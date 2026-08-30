from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, status

from ...schemas import CatalogueResponse
from ...services.library_access import LibraryNotFoundError
from ..dependencies import (
    CatalogueServiceDependency,
    CurrentAuthDependency,
    LibraryAccessServiceDependency,
)


router = APIRouter(prefix="/libraries/{library_id}/catalogue", tags=["catalogue"])


@router.get("", response_model=CatalogueResponse)
def get_catalogue(
    library_id: UUID,
    service: CatalogueServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    search: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CatalogueResponse:
    try:
        access_service.require_catalogue(
            library_id=library_id, user_id=context.user_id
        )
    except LibraryNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Library not found",
        ) from exc
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

