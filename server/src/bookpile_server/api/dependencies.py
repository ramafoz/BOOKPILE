from typing import Annotated

from fastapi import Depends
from sqlalchemy.orm import Session

from ..database import get_session
from ..repositories.books import BookRepository
from ..services.catalogue import CatalogueService


SessionDependency = Annotated[Session, Depends(get_session)]


def get_catalogue_service(session: SessionDependency) -> CatalogueService:
    return CatalogueService(BookRepository(session))


CatalogueServiceDependency = Annotated[
    CatalogueService, Depends(get_catalogue_service)
]

