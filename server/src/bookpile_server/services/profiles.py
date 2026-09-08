from dataclasses import dataclass
from datetime import date
from uuid import UUID

from ..repositories.profiles import ProfileRepository


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


class ProfileNotFoundError(Exception):
    pass


@dataclass(frozen=True)
class ProfileProjection:
    user_id: UUID
    username: str
    display_name: str | None = None
    timezone: str | None = None
    gender: str | None = None
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
        if profile.gender in {"MALE", "FEMALE"}:
            pronoun = profile.gender
        elif profile.gender == "CUSTOM":
            pronoun = profile.preferred_pronoun
            neutral = profile.neutral_pronoun if pronoun == "NEUTRAL" else None
        return ProfileProjection(
            user_id=user.id,
            username=user.username,
            **values,
            profile_image_visible=can_see("profile_image"),
            preferred_pronoun=pronoun,
            neutral_pronoun=neutral,
        )
