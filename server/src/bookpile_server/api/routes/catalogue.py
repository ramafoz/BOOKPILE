from typing import Literal
from uuid import UUID

from datetime import timedelta

from fastapi import APIRouter, File, HTTPException, Query, Request, Response, UploadFile, status

from ...schemas import (
    BookResponse,
    BookSummary,
    BookWithPlacementWrite,
    BookWrite,
    CatalogueMetadataOptions,
    CatalogueResponse,
    ContributorResponse,
    ContributorRoleResponse,
    CoverMetadataResponse,
    DeleteBookRequest,
)
from ...services.catalogue import (
    BookRecord,
    CatalogueConflictError,
    CatalogueNotFoundError,
    CatalogueValidationError,
)
from ...cover_images import InvalidCoverImage, process_cover_image
from ...config import get_settings
from ...services.covers import CoverNotFoundError, CoverStorageError
from ...services.rate_limits import RateLimitExceededError, RateLimitPolicy
from ...services.library_access import (
    LibraryNotFoundError,
    LibraryOwnerRequiredError,
)
from ...services.physical_library import (
    PhysicalLibraryConflictError,
    PhysicalLibraryNotFoundError,
    PhysicalLibraryValidationError,
)
from ..dependencies import (
    CatalogueServiceDependency,
    CoverServiceDependency,
    CsrfDependency,
    CurrentAuthDependency,
    LibraryAccessServiceDependency,
    PhysicalLibraryServiceDependency,
    RateLimiterDependency,
)


router = APIRouter(prefix="/libraries/{library_id}/catalogue", tags=["catalogue"])


def catalogue_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (LibraryNotFoundError, LibraryOwnerRequiredError)):
        return HTTPException(status_code=404, detail="Library not found")
    if isinstance(exc, CatalogueNotFoundError):
        return HTTPException(status_code=404, detail="Book not found")
    if isinstance(exc, CatalogueValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, CatalogueConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def book_response(record: BookRecord, *, detail: bool) -> BookResponse | BookSummary:
    book = record.book
    contributors = [
        ContributorResponse(
            id=item.id,
            role_code=item.role_code,
            role_label=role.label,
            position=item.position,
            name=item.name,
        )
        for item, role in record.contributors
    ]
    common = {
        "id": book.id,
        "title": book.title,
        "author": book.author,
        "display_author": record.display_author,
        "subtitle": book.subtitle,
        "page_count": book.page_count,
        "publisher": book.publisher,
        "current_ed_year": book.current_ed_year,
        "language": book.language,
        "fiction_category": book.fiction_category,
        "binding": book.binding,
        "publication_type": book.publication_type,
        "genre_text": book.genre_text,
        "series_name": book.series_name,
        "series_volume": book.series_volume,
        "contributors": contributors,
        "cover": CoverMetadataResponse(
            width_px=book.cover.width_px,
            height_px=book.cover.height_px,
            byte_size=book.cover.byte_size,
            updated_at=book.cover.updated_at,
        ) if book.cover else None,
        "created_at": book.created_at,
        "updated_at": book.updated_at,
    }
    if not detail:
        return BookSummary(**common)
    return BookResponse(
        **common,
        library_id=book.library_id,
        isbn_10=book.isbn_10,
        isbn_13=book.isbn_13,
        original_publication_year=book.original_publication_year,
        original_language=book.original_language,
        translation_status=book.translation_status,
        edition_number=book.edition_number,
        notes=book.notes,
        acquisition_date=book.acquisition_date,
        is_original_collection=book.is_original_collection,
        height_mm=book.height_mm,
        width_mm=book.width_mm,
        thickness_mm=book.thickness_mm,
    )


def cover_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (CatalogueNotFoundError, CoverNotFoundError, LibraryNotFoundError, LibraryOwnerRequiredError)):
        return HTTPException(status_code=404, detail="Cover not found")
    if isinstance(exc, InvalidCoverImage):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, CoverStorageError):
        return HTTPException(status_code=503, detail=str(exc))
    if isinstance(exc, CatalogueConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


@router.get("", response_model=CatalogueResponse)
def get_catalogue(
    library_id: UUID,
    service: CatalogueServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    search: str | None = Query(default=None, max_length=200),
    isbn: str | None = Query(default=None, max_length=40),
    language: list[str] = Query(default=[]),
    original_language: list[str] = Query(default=[]),
    translation_status: list[str] = Query(default=[]),
    genre: list[str] = Query(default=[]),
    publisher: list[str] = Query(default=[]),
    fiction_category: list[str] = Query(default=[]),
    binding: list[str] = Query(default=[]),
    publication_type: list[str] = Query(default=[]),
    series_name: list[str] = Query(default=[]),
    series_state: Literal["ANY", "YES", "NO"] = "ANY",
    author_structure: Literal["ANY", "SINGLE", "MULTIPLE"] = "ANY",
    page_min: int | None = Query(default=None, ge=1),
    page_max: int | None = Query(default=None, ge=1),
    year_field: Literal[
        "current_ed_year", "original_publication_year"
    ] = "current_ed_year",
    year_min: int | None = Query(default=None, ge=1000, le=9999),
    year_max: int | None = Query(default=None, ge=1000, le=9999),
    sort_by: Literal[
        "title",
        "author",
        "created_at",
        "updated_at",
        "page_count",
        "publisher",
        "current_ed_year",
        "original_publication_year",
        "acquisition_date",
    ] = "title",
    sort_order: Literal["asc", "desc"] = "asc",
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> CatalogueResponse:
    try:
        access = access_service.require_catalogue(
            library_id=library_id, user_id=context.user_id
        )
        page = service.list_books(
            library_id,
            search=search,
            isbn=isbn,
            languages=language,
            original_languages=original_language,
            translation_statuses=translation_status,
            genres=genre,
            publishers=publisher,
            fiction_categories=fiction_category,
            bindings=binding,
            publication_types=publication_type,
            series_names=series_name,
            series_state=series_state,
            author_structure=author_structure,
            page_min=page_min,
            page_max=page_max,
            year_field=year_field,
            year_min=year_min,
            year_max=year_max,
            sort_by=sort_by,
            sort_order=sort_order,
            limit=limit,
            offset=offset,
        )
    except (LibraryNotFoundError, CatalogueValidationError) as exc:
        raise catalogue_error(exc) from exc
    return CatalogueResponse(
        library_id=library_id,
        role=access.role,
        can_edit=access.is_owner,
        total=page.total,
        limit=page.limit,
        offset=page.offset,
        books=[book_response(record, detail=False) for record in page.records],
    )


@router.get("/metadata-options", response_model=CatalogueMetadataOptions)
def get_metadata_options(
    library_id: UUID,
    service: CatalogueServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
) -> CatalogueMetadataOptions:
    try:
        access_service.require_catalogue(library_id=library_id, user_id=context.user_id)
    except LibraryNotFoundError as exc:
        raise catalogue_error(exc) from exc
    options = service.metadata_options(library_id)
    return CatalogueMetadataOptions(
        languages=options.languages,
        original_languages=options.original_languages,
        publishers=options.publishers,
        genres=options.genres,
        series_names=options.series_names,
        contributor_roles=[
            ContributorRoleResponse(
                code=role.code, label=role.label, sort_order=role.sort_order
            )
            for role in options.roles
        ],
    )


@router.get("/{book_id}", response_model=BookResponse)
def get_book(
    library_id: UUID,
    book_id: UUID,
    service: CatalogueServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
) -> BookResponse:
    try:
        access_service.require_catalogue(library_id=library_id, user_id=context.user_id)
        return book_response(service.get_book(library_id, book_id), detail=True)
    except (LibraryNotFoundError, CatalogueNotFoundError) as exc:
        raise catalogue_error(exc) from exc


@router.post("", response_model=BookResponse, status_code=status.HTTP_201_CREATED)
def create_book(
    library_id: UUID,
    payload: BookWrite,
    service: CatalogueServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> BookResponse:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        record = service.create_book(
            library_id=library_id, actor_user_id=context.user_id, payload=payload
        )
        return book_response(record, detail=True)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        CatalogueValidationError,
        CatalogueConflictError,
    ) as exc:
        raise catalogue_error(exc) from exc


@router.post(
    "/with-placement",
    response_model=BookResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_book_with_placement(
    library_id: UUID,
    payload: BookWithPlacementWrite,
    service: CatalogueServiceDependency,
    physical_service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> BookResponse:
    """Create the catalogue record and its initial placement atomically."""
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        record = service.create_book(
            library_id=library_id,
            actor_user_id=context.user_id,
            payload=payload.book,
            commit=False,
        )
        physical_service.place_book(
            library_id=library_id,
            book_id=record.book.id,
            actor_user_id=context.user_id,
            payload=payload.placement,
        )
        return book_response(service.get_book(library_id, record.book.id), detail=True)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        CatalogueValidationError,
        CatalogueConflictError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryValidationError,
        PhysicalLibraryConflictError,
    ) as exc:
        service.rollback()
        if isinstance(exc, (PhysicalLibraryNotFoundError, PhysicalLibraryValidationError)):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if isinstance(exc, PhysicalLibraryConflictError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise catalogue_error(exc) from exc


@router.put("/{book_id}", response_model=BookResponse)
def update_book(
    library_id: UUID,
    book_id: UUID,
    payload: BookWrite,
    service: CatalogueServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> BookResponse:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        record = service.update_book(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
        return book_response(record, detail=True)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        CatalogueNotFoundError,
        CatalogueValidationError,
        CatalogueConflictError,
    ) as exc:
        raise catalogue_error(exc) from exc


@router.put("/{book_id}/with-placement", response_model=BookResponse)
def update_book_with_placement(
    library_id: UUID,
    book_id: UUID,
    payload: BookWithPlacementWrite,
    service: CatalogueServiceDependency,
    physical_service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> BookResponse:
    """Update catalogue metadata and placement in one database transaction."""
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        service.update_book(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            payload=payload.book,
            commit=False,
        )
        physical_service.place_book(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            payload=payload.placement,
        )
        return book_response(service.get_book(library_id, book_id), detail=True)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        CatalogueNotFoundError,
        CatalogueValidationError,
        CatalogueConflictError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryValidationError,
        PhysicalLibraryConflictError,
    ) as exc:
        service.rollback()
        if isinstance(exc, (PhysicalLibraryNotFoundError, PhysicalLibraryValidationError)):
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        if isinstance(exc, PhysicalLibraryConflictError):
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        raise catalogue_error(exc) from exc


@router.delete("/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(
    library_id: UUID,
    book_id: UUID,
    payload: DeleteBookRequest,
    service: CatalogueServiceDependency,
    cover_service: CoverServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        cover_key = cover_service.object_key(library_id, book_id)
        service.delete_book(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            confirmation_title=payload.confirmation_title,
        )
        cover_service.delete_object_after_book(cover_key)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        CatalogueNotFoundError,
        CatalogueValidationError,
        CatalogueConflictError,
    ) as exc:
        raise catalogue_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{book_id}/cover")
def get_book_cover(
    library_id: UUID,
    book_id: UUID,
    cover_service: CoverServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
) -> Response:
    try:
        access_service.require_catalogue(library_id=library_id, user_id=context.user_id)
        stored = cover_service.get(library_id, book_id)
        return Response(
            content=stored.content,
            media_type="image/webp",
            headers={
                "Cache-Control": "no-store, private",
                "Content-Disposition": "inline",
                "X-Content-Type-Options": "nosniff",
            },
        )
    except (LibraryNotFoundError, CatalogueNotFoundError, CoverNotFoundError, CoverStorageError) as exc:
        raise cover_error(exc) from exc


@router.put("/{book_id}/cover", response_model=CoverMetadataResponse)
async def put_book_cover(
    library_id: UUID,
    book_id: UUID,
    request: Request,
    cover_service: CoverServiceDependency,
    access_service: LibraryAccessServiceDependency,
    limiter: RateLimiterDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
    cover: UploadFile = File(...),
) -> CoverMetadataResponse:
    settings = get_settings()
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        limiter.enforce(
            RateLimitPolicy("cover_upload", settings.cover_upload_attempts_per_hour, timedelta(hours=1)),
            key=str(context.user_id),
            ip_address=request.client.host if request.client else None,
        )
        content = await cover.read(settings.cover_max_upload_bytes + 1)
        processed = process_cover_image(content, settings)
        saved = cover_service.replace(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            image=processed,
        )
        return CoverMetadataResponse(
            width_px=saved.width_px,
            height_px=saved.height_px,
            byte_size=saved.byte_size,
            updated_at=saved.updated_at,
        )
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many cover uploads. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except (LibraryNotFoundError, LibraryOwnerRequiredError, CatalogueNotFoundError, InvalidCoverImage, CoverStorageError, CatalogueConflictError) as exc:
        raise cover_error(exc) from exc
    finally:
        await cover.close()


@router.delete("/{book_id}/cover", status_code=status.HTTP_204_NO_CONTENT)
def delete_book_cover(
    library_id: UUID,
    book_id: UUID,
    cover_service: CoverServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        cover_service.remove(
            library_id=library_id, book_id=book_id, actor_user_id=context.user_id
        )
    except (LibraryNotFoundError, LibraryOwnerRequiredError, CatalogueNotFoundError, CoverNotFoundError, CoverStorageError) as exc:
        raise cover_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
