from uuid import UUID

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session, aliased

from ..models import (
    Library,
    LibraryMembership,
    User,
    UserProfile,
    UserProfileFieldVisibility,
    UserProfileImage,
)
from ..services.storage_transactions import commit_with_storage


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_user(self, user_id: UUID) -> User | None:
        return self.session.get(User, user_id)

    def find_profile(self, user_id: UUID) -> UserProfile | None:
        return self.session.get(UserProfile, user_id)

    def find_image(self, user_id: UUID) -> UserProfileImage | None:
        return self.session.get(UserProfileImage, user_id)

    def visibilities(self, user_id: UUID) -> dict[str, str]:
        return {
            item.field_name: item.visibility
            for item in self.session.scalars(
                select(UserProfileFieldVisibility).where(
                    UserProfileFieldVisibility.user_id == user_id
                )
            )
        }

    def share_active_library(self, first_user_id: UUID, second_user_id: UUID) -> bool:
        first = aliased(LibraryMembership)
        second = aliased(LibraryMembership)
        return bool(
            self.session.scalar(
                select(
                    exists()
                    .where(first.user_id == first_user_id)
                    .where(second.user_id == second_user_id)
                    .where(second.library_id == first.library_id)
                    .where(Library.id == first.library_id)
                    .where(Library.state == "active")
                )
            )
        )

    def save_profile(
        self,
        profile: UserProfile,
        visibilities: dict[str, str],
    ) -> None:
        self.session.add(profile)
        self.session.execute(
            delete(UserProfileFieldVisibility).where(
                UserProfileFieldVisibility.user_id == profile.user_id
            )
        )
        self.session.add_all(
            UserProfileFieldVisibility(
                user_id=profile.user_id,
                field_name=field,
                visibility=visibility,
            )
            for field, visibility in visibilities.items()
        )
        commit_with_storage(self.session)

    def save_image(self, image: UserProfileImage) -> None:
        self.session.add(image)
        commit_with_storage(self.session)

    def delete_image(self, image: UserProfileImage) -> None:
        self.session.delete(image)
        commit_with_storage(self.session)

    def rollback(self) -> None:
        self.session.rollback()
