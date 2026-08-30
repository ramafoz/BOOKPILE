from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, Response, status

from ...config import get_settings
from ...email_delivery import EmailDeliveryError
from ...schemas import (
    AccountTokenRequest,
    CurrentUserResponse,
    EmailAddressRequest,
    LoginRequest,
    LoginResponse,
    PasswordResetConfirmRequest,
    RegisterAccountRequest,
    RegisterAccountResponse,
)
from ...services.account_actions import (
    InvalidAccountActionTokenError,
    PasswordResetValidationError,
)
from ...services.account_invitations import (
    AccountInvitationError,
    RegistrationConflictError,
    RegistrationValidationError,
)
from ...services.auth import InvalidCredentialsError, LoginResult
from ...services.rate_limits import (
    RateLimitExceededError,
    RateLimiter,
    RateLimitPolicy,
)
from ..dependencies import (
    AccountActionServiceDependency,
    AccountInvitationServiceDependency,
    AuthServiceDependency,
    CsrfDependency,
    CurrentAuthDependency,
    RateLimiterDependency,
)


router = APIRouter(prefix="/auth", tags=["authentication"])

REGISTER_IP = RateLimitPolicy("register_ip", 10, timedelta(hours=1))
REGISTER_INVITATION = RateLimitPolicy("register_invitation", 10, timedelta(hours=1))
LOGIN_IP = RateLimitPolicy("login_ip", 60, timedelta(minutes=15))
LOGIN_IDENTITY = RateLimitPolicy("login_identity", 20, timedelta(minutes=15))
EMAIL_ACTION_IP = RateLimitPolicy("email_action_ip", 10, timedelta(hours=1))
VERIFICATION_EMAIL = RateLimitPolicy("verification_email", 5, timedelta(hours=1))
PASSWORD_RESET_EMAIL = RateLimitPolicy("password_reset_email", 5, timedelta(hours=1))
TOKEN_CONFIRM_IP = RateLimitPolicy("token_confirm_ip", 30, timedelta(minutes=15))
TOKEN_CONFIRM_VALUE = RateLimitPolicy("token_confirm_value", 10, timedelta(minutes=15))


def request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


def enforce_rate_limit(
    limiter: RateLimiter,
    policy: RateLimitPolicy,
    *,
    key: str,
    request: Request,
) -> None:
    try:
        limiter.enforce(
            policy,
            key=key,
            ip_address=request_ip(request),
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


def set_auth_cookies(response: Response, result: LoginResult) -> None:
    settings = get_settings()
    max_age = max(
        0, int((result.absolute_expires_at - datetime.now(UTC)).total_seconds())
    )
    response.set_cookie(
        key=settings.session_cookie_name,
        value=result.raw_session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/v1",
    )
    response.set_cookie(
        key=settings.csrf_cookie_name,
        value=result.raw_csrf_token,
        max_age=max_age,
        httponly=False,
        secure=settings.session_cookie_secure,
        samesite="lax",
        # The SPA is served from `/` and must be able to read this non-secret
        # double-submit value before sending it in X-CSRF-Token.
        path="/",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.session_cookie_name,
        path="/api/v1",
        secure=settings.session_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.delete_cookie(
        key=settings.csrf_cookie_name,
        path="/",
        secure=settings.session_cookie_secure,
        httponly=False,
        samesite="lax",
    )


@router.post(
    "/register",
    response_model=RegisterAccountResponse,
    status_code=status.HTTP_201_CREATED,
)
def register_account(
    payload: RegisterAccountRequest,
    request: Request,
    service: AccountInvitationServiceDependency,
    account_actions: AccountActionServiceDependency,
    rate_limiter: RateLimiterDependency,
) -> RegisterAccountResponse:
    enforce_rate_limit(
        rate_limiter,
        REGISTER_IP,
        key=request_ip(request) or "unknown",
        request=request,
    )
    enforce_rate_limit(
        rate_limiter,
        REGISTER_INVITATION,
        key=payload.invitation_token,
        request=request,
    )
    try:
        account = service.register(
            raw_token=payload.invitation_token,
            email=payload.email,
            username=payload.username,
            password=payload.password,
            password_confirmation=payload.password_confirmation,
            ip_address=request_ip(request),
        )
    except RegistrationValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except AccountInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Account invitation is invalid or expired",
        ) from exc
    except RegistrationConflictError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Account could not be created",
        ) from exc
    try:
        verification_email_sent = account_actions.send_verification_for_user(
            account.user_id, ip_address=request_ip(request)
        )
    except EmailDeliveryError:
        # Registration is already safely committed. The user can retry through
        # the enumeration-safe resend endpoint.
        verification_email_sent = False
    return RegisterAccountResponse(
        user_id=account.user_id,
        username=account.username,
        state=account.state,
        verification_email_sent=verification_email_sent,
    )


@router.post("/verification/resend", status_code=status.HTTP_202_ACCEPTED)
def resend_verification(
    payload: EmailAddressRequest,
    request: Request,
    response: Response,
    service: AccountActionServiceDependency,
    rate_limiter: RateLimiterDependency,
) -> Response:
    enforce_rate_limit(
        rate_limiter,
        EMAIL_ACTION_IP,
        key=request_ip(request) or "unknown",
        request=request,
    )
    enforce_rate_limit(
        rate_limiter,
        VERIFICATION_EMAIL,
        key=payload.email.strip().lower(),
        request=request,
    )
    try:
        service.resend_verification(payload.email, ip_address=request_ip(request))
    except EmailDeliveryError:
        pass
    response.status_code = status.HTTP_202_ACCEPTED
    return response


@router.post("/verification/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_verification(
    payload: AccountTokenRequest,
    request: Request,
    response: Response,
    service: AccountActionServiceDependency,
    rate_limiter: RateLimiterDependency,
) -> Response:
    enforce_rate_limit(
        rate_limiter,
        TOKEN_CONFIRM_IP,
        key=request_ip(request) or "unknown",
        request=request,
    )
    enforce_rate_limit(
        rate_limiter,
        TOKEN_CONFIRM_VALUE,
        key=payload.token,
        request=request,
    )
    try:
        service.verify_email(payload.token, ip_address=request_ip(request))
    except InvalidAccountActionTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Verification link is invalid or expired",
        ) from exc
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/password-reset/request", status_code=status.HTTP_202_ACCEPTED)
def request_password_reset(
    payload: EmailAddressRequest,
    request: Request,
    response: Response,
    service: AccountActionServiceDependency,
    rate_limiter: RateLimiterDependency,
) -> Response:
    enforce_rate_limit(
        rate_limiter,
        EMAIL_ACTION_IP,
        key=request_ip(request) or "unknown",
        request=request,
    )
    enforce_rate_limit(
        rate_limiter,
        PASSWORD_RESET_EMAIL,
        key=payload.email.strip().lower(),
        request=request,
    )
    try:
        service.request_password_reset(
            payload.email, ip_address=request_ip(request)
        )
    except EmailDeliveryError:
        pass
    response.status_code = status.HTTP_202_ACCEPTED
    return response


@router.post("/password-reset/confirm", status_code=status.HTTP_204_NO_CONTENT)
def confirm_password_reset(
    payload: PasswordResetConfirmRequest,
    request: Request,
    response: Response,
    service: AccountActionServiceDependency,
    rate_limiter: RateLimiterDependency,
) -> Response:
    enforce_rate_limit(
        rate_limiter,
        TOKEN_CONFIRM_IP,
        key=request_ip(request) or "unknown",
        request=request,
    )
    enforce_rate_limit(
        rate_limiter,
        TOKEN_CONFIRM_VALUE,
        key=payload.token,
        request=request,
    )
    try:
        service.reset_password(
            raw_token=payload.token,
            password=payload.password,
            password_confirmation=payload.password_confirmation,
            ip_address=request_ip(request),
        )
    except PasswordResetValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except InvalidAccountActionTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Password reset link is invalid or expired",
        ) from exc
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.post("/login", response_model=LoginResponse)
def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    rate_limiter: RateLimiterDependency,
) -> LoginResponse:
    enforce_rate_limit(
        rate_limiter,
        LOGIN_IP,
        key=request_ip(request) or "unknown",
        request=request,
    )
    enforce_rate_limit(
        rate_limiter,
        LOGIN_IDENTITY,
        key=payload.identifier.strip().lower(),
        request=request,
    )
    try:
        result = service.login(
            identifier=payload.identifier,
            password=payload.password,
            remember_me=payload.remember_me,
            user_agent=request.headers.get("user-agent"),
            ip_address=request_ip(request),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        ) from exc

    # The session cookie is opaque and HttpOnly. JavaScript reads only the
    # separate CSRF cookie and mirrors it into the X-CSRF-Token header.
    set_auth_cookies(response, result)
    return LoginResponse(
        user_id=result.user_id,
        username=result.username,
        expires_at=result.expires_at,
        absolute_expires_at=result.absolute_expires_at,
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    service.logout(context, ip_address=request_ip(request))
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@router.get("/me", response_model=CurrentUserResponse)
def current_user(context: CurrentAuthDependency) -> CurrentUserResponse:
    return CurrentUserResponse(user_id=context.user_id, username=context.username)


@router.post("/session/rotate", response_model=LoginResponse)
def rotate_session(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> LoginResponse:
    result = service.rotate(
        context,
        user_agent=request.headers.get("user-agent"),
        ip_address=request_ip(request),
    )
    set_auth_cookies(response, result)
    return LoginResponse(
        user_id=result.user_id,
        username=result.username,
        expires_at=result.expires_at,
        absolute_expires_at=result.absolute_expires_at,
    )


@router.post("/sessions/revoke-all", status_code=status.HTTP_204_NO_CONTENT)
def revoke_all_sessions(
    request: Request,
    response: Response,
    service: AuthServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    service.revoke_all(context, ip_address=request_ip(request))
    clear_auth_cookies(response)
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
