from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from ..cover_images import ProcessedCover
from ..cover_storage import CoverStorage
from ..models import UserProfile, UserProfileImage
from ..repositories.profiles import ProfileRepository
from ..schemas import ProfileWrite


PROFILE_FIELDS = (
    "display_name",
    "timezone",
    "gender",
    "city",
    "state",
    "country",
    "date_of_birth",
    "profile_image",
)
PERSONAL_FIELDS = ("gender", "city", "state", "country", "date_of_birth")
GROUPED_PROFILE_FIELDS = ("display_name", "timezone", "personal_data", "profile_image")


class ProfileNotFoundError(Exception):
    pass


class ProfileImageStorageError(Exception):
    pass


@dataclass(frozen=True)
class ProfileProjection:
    user_id: UUID
    username: str
    display_name: str | None = None
    timezone: str | None = None
    gender: str | None = None
    custom_gender: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    date_of_birth: date | None = None
    profile_image_visible: bool = False
    preferred_pronoun: str | None = None
    neutral_pronoun: str | None = None


class ProfileService:
    def __init__(self, repository: ProfileRepository) -> None:
        self.repository = repository

    def project(self, *, target_user_id: UUID, actor_user_id: UUID) -> ProfileProjection:
        user = self.repository.find_user(target_user_id)
        if user is None or user.state != "active":
            raise ProfileNotFoundError
        profile = self.repository.find_profile(target_user_id)
        if profile is None:
            return ProfileProjection(user_id=user.id, username=user.username)

        own = target_user_id == actor_user_id
        shared = own or self.repository.share_active_library(target_user_id, actor_user_id)
        visibility = self.repository.visibilities(target_user_id)

        def can_see(field: str) -> bool:
            if own:
                return True
            rule = visibility.get(field, "PRIVATE")
            return rule == "AUTHENTICATED" or (
                rule == "SHARED_LIBRARY_MEMBERS" and shared
            )

        values = {
            field: getattr(profile, field) if can_see(field) else None
            for field in PROFILE_FIELDS
            if field != "profile_image"
        }
        pronoun = None
        neutral = None
        if profile.gender == "CUSTOM":
            pronoun = profile.preferred_pronoun
            neutral = profile.neutral_pronoun if pronoun == "NEUTRAL" else None
        return ProfileProjection(
            user_id=user.id,
            username=user.username,
            **values,
            custom_gender=(profile.custom_gender if can_see("gender") else None),
            profile_image_visible=(
                self.repository.find_image(target_user_id) is not None
                and can_see("profile_image")
            ),
            preferred_pronoun=pronoun,
            neutral_pronoun=neutral,
        )

    def own_profile(self, user_id: UUID) -> tuple[ProfileProjection, dict[str, str]]:
        projection = self.project(target_user_id=user_id, actor_user_id=user_id)
        stored = self.repository.visibilities(user_id)
        # Old per-field values are collapsed to the most restrictive audience.
        # A subsequent save makes the personal-data group homogeneous.
        rank = {"PRIVATE": 0, "SHARED_LIBRARY_MEMBERS": 1, "AUTHENTICATED": 2}
        personal = min(
            (stored.get(field, "PRIVATE") for field in PERSONAL_FIELDS),
            key=lambda item: rank[item],
        )
        visibility = {
            "display_name": stored.get("display_name", "PRIVATE"),
            "timezone": stored.get("timezone", "PRIVATE"),
            "personal_data": personal,
            "profile_image": stored.get("profile_image", "PRIVATE"),
        }
        return projection, visibility

    def update(self, *, user_id: UUID, payload: ProfileWrite) -> None:
        if self.repository.find_user(user_id) is None:
            raise ProfileNotFoundError
        profile = self.repository.find_profile(user_id) or UserProfile(user_id=user_id)
        for field in (
            "display_name", "timezone", "gender", "custom_gender",
            "preferred_pronoun", "neutral_pronoun", "city", "state",
            "country", "date_of_birth",
        ):
            setattr(profile, field, getattr(payload, field))
        personal_visibility = payload.visibilities.get("personal_data", "PRIVATE")
        visibility = {
            "display_name": payload.visibilities.get("display_name", "PRIVATE"),
            "timezone": payload.visibilities.get("timezone", "PRIVATE"),
            "profile_image": payload.visibilities.get("profile_image", "PRIVATE"),
            **{field: personal_visibility for field in PERSONAL_FIELDS},
        }
        self.repository.save_profile(profile, visibility)


class ProfileImageService:
    def __init__(self, repository: ProfileRepository, storage: CoverStorage) -> None:
        self.repository = repository
        self.storage = storage

    def read(self, user_id: UUID) -> tuple[UserProfileImage, bytes]:
        image = self.repository.find_image(user_id)
        if image is None:
            raise ProfileNotFoundError
        try:
            return image, self.storage.read(image.object_key)
        except OSError as exc:
            raise ProfileImageStorageError("The profile image is temporarily unavailable.") from exc

    def replace(self, *, user_id: UUID, image: ProcessedCover) -> UserProfileImage:
        old = self.repository.find_image(user_id)
        old_key = old.object_key if old else None
        object_key = f"profile-images/{uuid4().hex}.webp"
        try:
            self.storage.put(object_key, image.content)
        except OSError as exc:
            raise ProfileImageStorageError("BOOKPILE could not store this profile image.") from exc
        now = datetime.now(UTC)
        record = old or UserProfileImage(user_id=user_id)
        record.object_key = object_key
        record.media_type = "image/webp"
        record.byte_size = len(image.content)
        record.width_px = image.width_px
        record.height_px = image.height_px
        record.sha256 = image.sha256
        record.updated_at = now
        try:
            self.repository.save_image(record)
        except Exception:
            self.storage.delete(object_key)
            raise
        if old_key and old_key != object_key:
            try:
                self.storage.delete(old_key)
            except OSError:
                pass
        return record

    def remove(self, user_id: UUID) -> None:
        image = self.repository.find_image(user_id)
        if image is None:
            raise ProfileNotFoundError
        object_key = image.object_key
        self.repository.delete_image(image)
        try:
            self.storage.delete(object_key)
        except OSError:
            pass
