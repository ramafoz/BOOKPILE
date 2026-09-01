from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from ..database import get_session
from ..email_delivery import EmailSender, SmtpEmailSender
from ..repositories.account_actions import AccountActionRepository
from ..repositories.rate_limits import RateLimitRepository
from ..repositories.books import BookRepository
from ..repositories.covers import CoverRepository
from ..repositories.libraries import LibraryRepository
from ..repositories.auth import AuthRepository
from ..repositories.account_invitations import AccountInvitationRepository
from ..services.account_invitations import AccountInvitationService
from ..services.account_actions import AccountActionService
from ..services.rate_limits import RateLimiter
from ..config import get_settings
from ..services.auth import (
    AuthContext,
    AuthService,
    InvalidCsrfTokenError,
    InvalidSessionError,
)
from ..services.catalogue import CatalogueService
from ..services.covers import CoverService
from ..cover_storage import FilesystemCoverStorage
from ..services.library_access import LibraryAccessService
from ..services.libraries import LibraryService


SessionDependency = Annotated[Session, Depends(get_session)]


def get_catalogue_service(session: SessionDependency) -> CatalogueService:
    return CatalogueService(BookRepository(session))


CatalogueServiceDependency = Annotated[
    CatalogueService, Depends(get_catalogue_service)
]


def get_cover_service(session: SessionDependency) -> CoverService:
    settings = get_settings()
    return CoverService(
        CoverRepository(session),
        BookRepository(session),
        FilesystemCoverStorage(settings.private_object_root),
        settings,
    )


CoverServiceDependency = Annotated[CoverService, Depends(get_cover_service)]


def get_library_access_service(
    session: SessionDependency,
) -> LibraryAccessService:
    return LibraryAccessService(LibraryRepository(session))


LibraryAccessServiceDependency = Annotated[
    LibraryAccessService, Depends(get_library_access_service)
]


def get_library_service(session: SessionDependency) -> LibraryService:
    return LibraryService(LibraryRepository(session))


LibraryServiceDependency = Annotated[
    LibraryService, Depends(get_library_service)
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


def get_email_sender() -> EmailSender:
    return SmtpEmailSender(get_settings())


EmailSenderDependency = Annotated[EmailSender, Depends(get_email_sender)]


def get_account_action_service(
    session: SessionDependency,
    email_sender: EmailSenderDependency,
) -> AccountActionService:
    return AccountActionService(
        AccountActionRepository(session), email_sender, get_settings()
    )


AccountActionServiceDependency = Annotated[
    AccountActionService, Depends(get_account_action_service)
]


def get_rate_limiter(session: SessionDependency) -> RateLimiter:
    settings = get_settings()
    return RateLimiter(
        RateLimitRepository(session), settings.rate_limit_key_secret
    )


RateLimiterDependency = Annotated[RateLimiter, Depends(get_rate_limiter)]


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

