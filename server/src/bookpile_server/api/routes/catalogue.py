from uuid import UUID

from fastapi import APIRouter, Query

from ...schemas import CatalogueResponse
from ..dependencies import CatalogueServiceDependency


router = APIRouter(prefix="/libraries/{library_id}/catalogue", tags=["catalogue"])


@router.get("", response_model=CatalogueResponse)
def get_catalogue(
    library_id: UUID,
    service: CatalogueServiceDependency,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CatalogueResponse:
    page = service.list_books(
        library_id,
        search=search,
        limit=limit,
        offset=offset,
    )
    return CatalogueResponse(
        library_id=library_id,
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        books=page.books,
    )

