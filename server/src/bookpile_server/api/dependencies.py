from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..database import get_session
from ..repositories.books import BookRepository
from ..repositories.auth import AuthRepository
from ..services.auth import AuthService
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

