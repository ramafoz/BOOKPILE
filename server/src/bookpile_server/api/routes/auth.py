from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException, Request, Response, status

from ...config import get_settings
from ...schemas import LoginRequest, LoginResponse
from ...services.auth import InvalidCredentialsError
from ..dependencies import AuthServiceDependency


router = APIRouter(prefix="/auth", tags=["authentication"])


def request_ip(request: Request) -> str | None:
    return request.client.host if request.client else None


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

    settings = get_settings()
    max_age = max(
        0, int((result.absolute_expires_at - datetime.now(UTC)).total_seconds())
    )
    # The cookie contains the opaque credential; only its hash is persisted.
    response.set_cookie(
        key=settings.session_cookie_name,
        value=result.raw_session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.session_cookie_secure,
        samesite="lax",
        path="/api/v1",
    )
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
) -> Response:
    settings = get_settings()
    service.logout(
        request.cookies.get(settings.session_cookie_name),
        ip_address=request_ip(request),
    )
    response.delete_cookie(key=settings.session_cookie_name, path="/api/v1")
    response.status_code = status.HTTP_204_NO_CONTENT
    return response
