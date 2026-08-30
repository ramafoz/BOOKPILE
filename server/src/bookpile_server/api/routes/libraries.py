from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from ...models import LibraryMembership
from ...schemas import (
    AcceptLibraryInvitationRequest,
    ChangeLibraryMemberRequest,
    CreateLibraryInvitationRequest,
    CreateLibraryRequest,
    CreatedLibraryInvitationResponse,
    LibraryMemberResponse,
    LibrarySummaryResponse,
    ReadingPerspectiveResponse,
    SelectReadingPerspectiveRequest,
)
from ...services.libraries import (
    InvalidLibraryInvitationError,
    LibraryConflictError,
    FinalOwnerError,
    LibraryReauthenticationError,
    LibraryService,
    LibraryValidationError,
)
from ...services.library_access import (
    LibraryNotFoundError,
    LibraryOwnerRequiredError,
)
from ..dependencies import (
    CsrfDependency,
    CurrentAuthDependency,
    LibraryServiceDependency,
)


router = APIRouter(tags=["libraries"])


def library_summary(membership: LibraryMembership) -> LibrarySummaryResponse:
    return LibrarySummaryResponse(
        library_id=membership.library_id,
        name=membership.library.name,
        slug=membership.library.slug,
        role=membership.role,
        viewer_scope=membership.viewer_scope,
        selected_reading_user_id=membership.selected_reading_user_id,
        can_view_map=(
            membership.role == "OWNER"
            or membership.viewer_scope == "CATALOG_AND_MAP"
        ),
    )


def member_response(membership: LibraryMembership) -> LibraryMemberResponse:
    return LibraryMemberResponse(
        user_id=membership.user_id,
        username=membership.user.username,
        role=membership.role,
        viewer_scope=membership.viewer_scope,
        selected_reading_user_id=membership.selected_reading_user_id,
        created_at=membership.created_at,
    )


def translate_library_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (LibraryNotFoundError, LibraryOwnerRequiredError)):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Library not found"
        )
    if isinstance(exc, LibraryValidationError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        )
    if isinstance(exc, LibraryConflictError):
        return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc))
    if isinstance(exc, LibraryReauthenticationError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Current password is incorrect",
        )
    if isinstance(exc, FinalOwnerError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The final Owner cannot be removed or downgraded.",
        )
    raise exc


@router.get("/libraries", response_model=list[LibrarySummaryResponse])
def list_libraries(
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
) -> list[LibrarySummaryResponse]:
    return [library_summary(item) for item in service.list_for_user(context.user_id)]


@router.post(
    "/libraries",
    response_model=LibrarySummaryResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_library(
    payload: CreateLibraryRequest,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> LibrarySummaryResponse:
    try:
        membership = service.create(user_id=context.user_id, name=payload.name)
    except (LibraryValidationError, LibraryConflictError) as exc:
        raise translate_library_error(exc) from exc
    return library_summary(membership)


@router.get(
    "/libraries/{library_id}/members",
    response_model=list[LibraryMemberResponse],
)
def list_members(
    library_id: UUID,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
) -> list[LibraryMemberResponse]:
    try:
        memberships = service.list_members(
            library_id=library_id, actor_user_id=context.user_id
        )
    except (LibraryNotFoundError, LibraryOwnerRequiredError) as exc:
        raise translate_library_error(exc) from exc
    return [member_response(item) for item in memberships]


@router.post(
    "/libraries/{library_id}/invitations",
    response_model=CreatedLibraryInvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_invitation(
    library_id: UUID,
    payload: CreateLibraryInvitationRequest,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> CreatedLibraryInvitationResponse:
    try:
        result = service.create_invitation(
            library_id=library_id,
            actor_user_id=context.user_id,
            role=payload.role,
            viewer_scope=payload.viewer_scope,
            acknowledge_equal_owner_power=payload.acknowledge_equal_owner_power,
        )
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        LibraryValidationError,
    ) as exc:
        raise translate_library_error(exc) from exc
    return CreatedLibraryInvitationResponse(
        invitation_id=result.invitation_id,
        invitation_token=result.raw_token,
        expires_at=result.expires_at,
    )


@router.delete(
    "/libraries/{library_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def revoke_invitation(
    library_id: UUID,
    invitation_id: UUID,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        service.revoke_invitation(
            library_id=library_id,
            invitation_id=invitation_id,
            actor_user_id=context.user_id,
        )
    except (LibraryNotFoundError, LibraryOwnerRequiredError) as exc:
        raise translate_library_error(exc) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/library-invitations/accept",
    response_model=LibrarySummaryResponse,
)
def accept_invitation(
    payload: AcceptLibraryInvitationRequest,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> LibrarySummaryResponse:
    try:
        membership = service.accept_invitation(
            raw_token=payload.invitation_token,
            user_id=context.user_id,
        )
    except InvalidLibraryInvitationError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Library invitation is invalid or expired",
        ) from exc
    except LibraryConflictError as exc:
        raise translate_library_error(exc) from exc
    return library_summary(membership)


@router.patch(
    "/libraries/{library_id}/members/{target_user_id}",
    response_model=LibraryMemberResponse | None,
)
def change_member(
    library_id: UUID,
    target_user_id: UUID,
    payload: ChangeLibraryMemberRequest,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> LibraryMemberResponse | None:
    try:
        membership = service.change_member(
            library_id=library_id,
            actor_user_id=context.user_id,
            target_user_id=target_user_id,
            action=payload.action,
            viewer_scope=payload.viewer_scope,
            current_password=payload.current_password,
            acknowledge_equal_owner_power=payload.acknowledge_equal_owner_power,
        )
    except (
        LibraryNotFoundError,
        LibraryOwnerRequiredError,
        LibraryValidationError,
        LibraryReauthenticationError,
        FinalOwnerError,
    ) as exc:
        raise translate_library_error(exc) from exc
    return member_response(membership) if membership is not None else None


def perspective_responses(
    actor: LibraryMembership, owners: list[LibraryMembership]
) -> list[ReadingPerspectiveResponse]:
    return [
        ReadingPerspectiveResponse(
            user_id=owner.user_id,
            username=owner.user.username,
            selected=actor.selected_reading_user_id == owner.user_id,
            writable=(actor.role == "OWNER" and actor.user_id == owner.user_id),
        )
        for owner in owners
    ]


@router.get(
    "/libraries/{library_id}/reading-perspectives",
    response_model=list[ReadingPerspectiveResponse],
)
def list_reading_perspectives(
    library_id: UUID,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
) -> list[ReadingPerspectiveResponse]:
    try:
        actor, owners = service.list_reading_perspectives(
            library_id=library_id, actor_user_id=context.user_id
        )
    except LibraryNotFoundError as exc:
        raise translate_library_error(exc) from exc
    return perspective_responses(actor, owners)


@router.put(
    "/libraries/{library_id}/reading-perspective",
    response_model=list[ReadingPerspectiveResponse],
)
def select_reading_perspective(
    library_id: UUID,
    payload: SelectReadingPerspectiveRequest,
    service: LibraryServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> list[ReadingPerspectiveResponse]:
    try:
        service.select_reading_perspective(
            library_id=library_id,
            actor_user_id=context.user_id,
            selected_user_id=payload.user_id,
        )
        actor, owners = service.list_reading_perspectives(
            library_id=library_id, actor_user_id=context.user_id
        )
    except (LibraryNotFoundError, LibraryValidationError) as exc:
        raise translate_library_error(exc) from exc
    return perspective_responses(actor, owners)
