from datetime import timedelta
from uuid import UUID

from fastapi import APIRouter, File, HTTPException, Request, Response, UploadFile, status

from ...config import get_settings
from ...cover_images import InvalidCoverImage, process_cover_image
from ...schemas import (
    ChangePasswordWrite,
    PrivateAccountResponse,
    ProfileResponse,
    ProfileWrite,
    StorageLibraryContributionResponse,
    StorageOverviewResponse,
)
from ...security.passwords import PasswordPolicyError
from ...services.auth import InvalidCredentialsError, PasswordConfirmationError
from ...services.profiles import ProfileImageStorageError, ProfileNotFoundError
from ...services.rate_limits import RateLimitExceededError, RateLimitPolicy
from ..dependencies import (
    CsrfDependency,
    AuthServiceDependency,
    CurrentAuthDependency,
    ProfileImageServiceDependency,
    ProfileServiceDependency,
    RateLimiterDependency,
    StorageServiceDependency,
)


router = APIRouter(tags=["profiles"])


@router.get("/account", response_model=PrivateAccountResponse)
def private_account(
    service: AuthServiceDependency,
    context: CurrentAuthDependency,
) -> PrivateAccountResponse:
    user = service.private_account(context)
    return PrivateAccountResponse(
        user_id=user.id,
        username=user.username,
        email=user.email,
        created_at=user.created_at,
    )


@router.put("/account/password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(
    payload: ChangePasswordWrite,
    request: Request,
    service: AuthServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        service.change_password(
            context,
            current_password=payload.current_password,
            new_password=payload.new_password,
            confirmation=payload.confirmation,
            ip_address=request.client.host if request.client else None,
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(status_code=403, detail="Current password is incorrect") from exc
    except (PasswordConfirmationError, PasswordPolicyError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def response_from_projection(projection, visibilities=None) -> ProfileResponse:
    return ProfileResponse(
        user_id=projection.user_id,
        username=projection.username,
        display_name=projection.display_name,
        timezone=projection.timezone,
        gender=projection.gender,
        custom_gender=projection.custom_gender,
        preferred_pronoun=projection.preferred_pronoun,
        neutral_pronoun=projection.neutral_pronoun,
        city=projection.city,
        state=projection.state,
        country=projection.country,
        date_of_birth=projection.date_of_birth,
        profile_image_visible=projection.profile_image_visible,
        visibilities=visibilities,
    )


@router.get("/account/profile", response_model=ProfileResponse)
def own_profile(
    service: ProfileServiceDependency,
    context: CurrentAuthDependency,
) -> ProfileResponse:
    projection, visibility = service.own_profile(context.user_id)
    return response_from_projection(projection, visibility)


@router.put("/account/profile", response_model=ProfileResponse)
def update_profile(
    payload: ProfileWrite,
    service: ProfileServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> ProfileResponse:
    service.update(user_id=context.user_id, payload=payload)
    projection, visibility = service.own_profile(context.user_id)
    return response_from_projection(projection, visibility)


@router.get("/profiles/{user_id}", response_model=ProfileResponse)
def projected_profile(
    user_id: UUID,
    service: ProfileServiceDependency,
    context: CurrentAuthDependency,
) -> ProfileResponse:
    try:
        return response_from_projection(
            service.project(target_user_id=user_id, actor_user_id=context.user_id)
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile not found") from exc


@router.get("/profiles/{user_id}/image")
def profile_image(
    user_id: UUID,
    profile_service: ProfileServiceDependency,
    image_service: ProfileImageServiceDependency,
    context: CurrentAuthDependency,
) -> Response:
    try:
        projection = profile_service.project(
            target_user_id=user_id, actor_user_id=context.user_id
        )
        if user_id != context.user_id and not projection.profile_image_visible:
            raise ProfileNotFoundError
        _metadata, content = image_service.read(user_id)
        return Response(
            content=content,
            media_type="image/webp",
            headers={"Cache-Control": "no-store"},
        )
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile image not found") from exc
    except ProfileImageStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.put("/account/profile/image", status_code=status.HTTP_204_NO_CONTENT)
async def replace_profile_image(
    request: Request,
    image_service: ProfileImageServiceDependency,
    limiter: RateLimiterDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
    image: UploadFile = File(...),
) -> Response:
    settings = get_settings()
    try:
        limiter.enforce(
            RateLimitPolicy(
                "profile_image_upload",
                settings.cover_upload_attempts_per_hour,
                timedelta(hours=1),
            ),
            key=str(context.user_id),
            ip_address=request.client.host if request.client else None,
        )
        content = await image.read(settings.cover_max_upload_bytes + 1)
        image_service.replace(
            user_id=context.user_id,
            image=process_cover_image(content, settings),
        )
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=429,
            detail="Too many profile image uploads. Please try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except InvalidCoverImage as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ProfileImageStorageError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        await image.close()


@router.delete("/account/profile/image", status_code=status.HTTP_204_NO_CONTENT)
def remove_profile_image(
    image_service: ProfileImageServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        image_service.remove(context.user_id)
    except ProfileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Profile image not found") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/account/storage", response_model=StorageOverviewResponse)
def storage_overview(
    service: StorageServiceDependency,
    context: CurrentAuthDependency,
) -> StorageOverviewResponse:
    overview = service.private_overview(context.user_id)
    return StorageOverviewResponse(
        libraries=[
            StorageLibraryContributionResponse(
                library_id=item.library_id,
                name=item.name,
                colour_key=item.colour_key,
                share_of_used=item.share_of_used,
                share_of_entitlement=item.share_of_entitlement,
            )
            for item in overview.libraries
        ],
        account_data_share_of_used=overview.account_data_share_of_used,
        account_data_share_of_entitlement=overview.account_data_share_of_entitlement,
        used_share_of_entitlement=overview.used_share_of_entitlement,
    )
