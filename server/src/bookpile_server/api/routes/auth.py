from datetime import UTC, datetime

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
from ..dependencies import (
    AccountActionServiceDependency,
    AccountInvitationServiceDependency,
    AuthServiceDependency,
    CsrfDependency,
    CurrentAuthDependency,
)


router = APIRouter(prefix="/auth", tags=["authentication"])


def request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


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
        path="/api/v1",
    )


def clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(key=settings.session_cookie_name, path="/api/v1")
    response.delete_cookie(key=settings.csrf_cookie_name, path="/api/v1")


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
) -> RegisterAccountResponse:
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
) -> Response:
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
) -> Response:
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
) -> Response:
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
) -> Response:
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
) -> LoginResponse:
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
