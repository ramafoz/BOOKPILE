from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from ...config import get_settings
from ...schemas import CurrentUserResponse, LoginRequest, LoginResponse
from ...services.auth import InvalidCredentialsError, LoginResult
from ..dependencies import (
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
