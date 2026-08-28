from uuid import UUID

from fastapi import APIRouter

from ...schemas import CatalogueResponse
from ..dependencies import CatalogueServiceDependency


router = APIRouter(prefix="/libraries/{library_id}/catalogue", tags=["catalogue"])


@router.get("", response_model=CatalogueResponse)
def get_catalogue(
    library_id: UUID,
    service: CatalogueServiceDependency,
) -> CatalogueResponse:
    books = service.list_books(library_id)
    return CatalogueResponse(library_id=library_id, books=books)

