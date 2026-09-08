from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session, aliased

from ..models import (
    Library,
    LibraryMembership,
    User,
    UserProfile,
    UserProfileFieldVisibility,
)


class ProfileRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def find_user(self, user_id: UUID) -> User | None:
        return self.session.get(User, user_id)

    def find_profile(self, user_id: UUID) -> UserProfile | None:
        return self.session.get(UserProfile, user_id)

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
