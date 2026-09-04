from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from ...schemas import (
    BookcaseResponse,
    BookcaseCreate,
    BookcaseWrite,
    BookPlacementWrite,
    ContainerResponse,
    ContainerUpdate,
    ContainerWrite,
    PhysicalDeleteRequest,
    PhysicalBookResponse,
    PhysicalLibraryResponse,
    RearrangementApplyRequest,
    RearrangementRequest,
    RearrangementResultResponse,
    ShelfResponse,
    ShelfUpdate,
    ShelfWrite,
    VisualLayoutWrite,
)
from ...services.library_access import (
    LibraryAccess,
    LibraryMapAccessDeniedError,
    LibraryNotFoundError,
    LibraryOwnerRequiredError,
)
from ...services.physical_library import (
    PhysicalHierarchy,
    PhysicalLibraryConflictError,
    PhysicalLibraryNotFoundError,
    PhysicalLibraryValidationError,
)
from ..dependencies import (
    CsrfDependency,
    CurrentAuthDependency,
    LibraryAccessServiceDependency,
    PhysicalLibraryServiceDependency,
)


router = APIRouter(
    prefix="/libraries/{library_id}/physical-library", tags=["physical-library"]
)


def physical_error(exc: Exception) -> HTTPException:
    if isinstance(
        exc,
        (
            LibraryNotFoundError,
            LibraryMapAccessDeniedError,
            LibraryOwnerRequiredError,
            PhysicalLibraryNotFoundError,
        ),
    ):
        return HTTPException(status_code=404, detail="Physical library not found")
    if isinstance(exc, PhysicalLibraryValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, PhysicalLibraryConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def physical_response(
    library_id: UUID, access: LibraryAccess, hierarchy: PhysicalHierarchy
) -> PhysicalLibraryResponse:
    containers_by_shelf: dict[UUID, list[ContainerResponse]] = {}
    for item in hierarchy.containers:
        containers_by_shelf.setdefault(item.shelf_id, []).append(
            ContainerResponse(
                id=item.id,
                shelf_id=item.shelf_id,
                container_type=item.container_type,
                layer=item.layer,
                container_number=item.container_number,
                book_count=hierarchy.book_counts.get(item.id, 0),
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    shelves_by_bookcase: dict[UUID, list[ShelfResponse]] = {}
    for item in hierarchy.shelves:
        containers = containers_by_shelf.get(item.id, [])
        shelves_by_bookcase.setdefault(item.bookcase_id, []).append(
            ShelfResponse(
                id=item.id,
                bookcase_id=item.bookcase_id,
                shelf_number=item.shelf_number,
                usable_height_mm=item.usable_height_mm,
                usable_width_mm=item.usable_width_mm,
                usable_depth_mm=item.usable_depth_mm,
                book_count=sum(container.book_count for container in containers),
                containers=containers,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )

    bookcases = []
    for item in hierarchy.bookcases:
        shelves = shelves_by_bookcase.get(item.id, [])
        bookcases.append(
            BookcaseResponse(
                id=item.id,
                name=item.name,
                description=item.description,
                height_mm=item.height_mm,
                width_mm=item.width_mm,
                depth_mm=item.depth_mm,
                book_count=sum(shelf.book_count for shelf in shelves),
                shelves=shelves,
                created_at=item.created_at,
                updated_at=item.updated_at,
            )
        )
    return PhysicalLibraryResponse(
        library_id=library_id,
        role=access.role,
        can_edit=access.is_owner,
        bookcases=bookcases,
        books=[
            PhysicalBookResponse(
                id=item.id,
                title=item.title,
                author=item.author,
                page_count=item.page_count,
                height_mm=item.height_mm,
                width_mm=item.width_mm,
                thickness_mm=item.thickness_mm,
                container_id=item.container_id,
                position=item.position,
            )
            for item in hierarchy.books
        ],
        layout=hierarchy.layout,
    )


def refreshed(
    library_id: UUID,
    access: LibraryAccess,
    service: PhysicalLibraryServiceDependency,
) -> PhysicalLibraryResponse:
    return physical_response(library_id, access, service.hierarchy(library_id))


@router.get("", response_model=PhysicalLibraryResponse)
def get_physical_library(
    library_id: UUID,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_map(
            library_id=library_id, user_id=context.user_id
        )
        return refreshed(library_id, access, service)
    except (LibraryNotFoundError, LibraryMapAccessDeniedError) as exc:
        raise physical_error(exc) from exc


@router.put("/books/{book_id}/placement", response_model=PhysicalLibraryResponse)
def update_book_placement(
    library_id: UUID,
    book_id: UUID,
    payload: BookPlacementWrite,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.place_book(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryValidationError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.post("/rearrangements/preview", response_model=RearrangementResultResponse)
def preview_rearrangement(
    library_id: UUID,
    payload: RearrangementRequest,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
) -> RearrangementResultResponse:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        return service.preview_rearrangement(library_id=library_id, payload=payload)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryValidationError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.post("/rearrangements/apply", response_model=RearrangementResultResponse)
def apply_rearrangement(
    library_id: UUID,
    payload: RearrangementApplyRequest,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> RearrangementResultResponse:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        return service.apply_rearrangement(
            library_id=library_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryValidationError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.put("/layout", response_model=PhysicalLibraryResponse)
def update_visual_layout(
    library_id: UUID,
    payload: VisualLayoutWrite,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.update_visual_layout(
            library_id=library_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryValidationError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.post(
    "/bookcases",
    response_model=PhysicalLibraryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_bookcase(
    library_id: UUID,
    payload: BookcaseCreate,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.create_bookcase(
            library_id=library_id, actor_user_id=context.user_id, payload=payload
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.put("/bookcases/{bookcase_id}", response_model=PhysicalLibraryResponse)
def update_bookcase(
    library_id: UUID,
    bookcase_id: UUID,
    payload: BookcaseWrite,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.update_bookcase(
            library_id=library_id,
            bookcase_id=bookcase_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.delete("/bookcases/{bookcase_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bookcase(
    library_id: UUID,
    bookcase_id: UUID,
    _payload: PhysicalDeleteRequest,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        service.delete_bookcase(
            library_id=library_id,
            bookcase_id=bookcase_id,
            actor_user_id=context.user_id,
        )
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/shelves",
    response_model=PhysicalLibraryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_shelf(
    library_id: UUID,
    payload: ShelfWrite,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.create_shelf(
            library_id=library_id, actor_user_id=context.user_id, payload=payload
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.put("/shelves/{shelf_id}", response_model=PhysicalLibraryResponse)
def update_shelf(
    library_id: UUID,
    shelf_id: UUID,
    payload: ShelfUpdate,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.update_shelf(
            library_id=library_id,
            shelf_id=shelf_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.delete("/shelves/{shelf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shelf(
    library_id: UUID,
    shelf_id: UUID,
    _payload: PhysicalDeleteRequest,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        service.delete_shelf(
            library_id=library_id,
            shelf_id=shelf_id,
            actor_user_id=context.user_id,
        )
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/containers",
    response_model=PhysicalLibraryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_container(
    library_id: UUID,
    payload: ContainerWrite,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.create_container(
            library_id=library_id, actor_user_id=context.user_id, payload=payload
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.put("/containers/{container_id}", response_model=PhysicalLibraryResponse)
def update_container(
    library_id: UUID,
    container_id: UUID,
    payload: ContainerUpdate,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> PhysicalLibraryResponse:
    try:
        access = access_service.require_owner(
            library_id=library_id, user_id=context.user_id
        )
        service.update_container(
            library_id=library_id,
            container_id=container_id,
            actor_user_id=context.user_id,
            payload=payload,
        )
        return refreshed(library_id, access, service)
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc


@router.delete("/containers/{container_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_container(
    library_id: UUID,
    container_id: UUID,
    _payload: PhysicalDeleteRequest,
    service: PhysicalLibraryServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        access_service.require_owner(library_id=library_id, user_id=context.user_id)
        service.delete_container(
            library_id=library_id,
            container_id=container_id,
            actor_user_id=context.user_id,
        )
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        PhysicalLibraryNotFoundError,
        PhysicalLibraryConflictError,
    ) as exc:
        raise physical_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
