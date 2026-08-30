from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_session
from ..repositories.books import BookRepository
from ..repositories.auth import AuthRepository
from ..repositories.account_invitations import AccountInvitationRepository
from ..services.account_invitations import AccountInvitationService
from ..config import get_settings
from ..services.auth import (
    AuthContext,
    AuthService,
    InvalidCsrfTokenError,
    InvalidSessionError,
)
from ..services.catalogue import CatalogueService


SessionDependency = Annotated[Session, Depends(get_session)]


def get_catalogue_service(session: SessionDependency) -> CatalogueService:
    return CatalogueService(BookRepository(session))


CatalogueServiceDependency = Annotated[
    CatalogueService, Depends(get_catalogue_service)
]


def get_auth_service(session: SessionDependency) -> AuthService:
    return AuthService(AuthRepository(session))


AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_account_invitation_service(
    session: SessionDependency,
) -> AccountInvitationService:
    return AccountInvitationService(AccountInvitationRepository(session))


AccountInvitationServiceDependency = Annotated[
    AccountInvitationService, Depends(get_account_invitation_service)
]


def get_current_auth(
    request: Request, service: AuthServiceDependency
) -> AuthContext:
    settings = get_settings()
    try:
        return service.authenticate(
            request.cookies.get(settings.session_cookie_name)
        )
    except InvalidSessionError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        ) from exc


CurrentAuthDependency = Annotated[AuthContext, Depends(get_current_auth)]


def require_csrf(
    context: CurrentAuthDependency,
    service: AuthServiceDependency,
    x_csrf_token: Annotated[
        str | None, Header(alias="X-CSRF-Token")
    ] = None,
) -> None:
    try:
        service.require_csrf(context, x_csrf_token)
    except InvalidCsrfTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid CSRF token",
        ) from exc


CsrfDependency = Annotated[None, Depends(require_csrf)]

