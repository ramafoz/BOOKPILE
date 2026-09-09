from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..models import (
    AccountDeletionTombstone,
    Library,
    LibraryMembership,
    User,
    UserProfileImage,
)
from .storage import StorageRepository


class AccountDeletionRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_storage_entitlements_first(self) -> None:
        StorageRepository(self.session).ensure_entitlements()

    def lock_user(self, user_id: UUID) -> User | None:
        return self.session.scalar(
            select(User).where(User.id == user_id).with_for_update()
        )

    def user_by_identifier(self, identifier: str) -> User | None:
        normalized = identifier.strip().lower()
        return self.session.scalar(
            select(User).where(
                (User.username == normalized) | (User.email == normalized)
            )
        )

    def active_memberships(self, user_id: UUID, *, lock: bool = False) -> list[LibraryMembership]:
        statement = (
            select(LibraryMembership)
            .join(Library)
            .options(joinedload(LibraryMembership.library))
            .where(
                LibraryMembership.user_id == user_id,
                Library.state == "active",
            )
            .order_by(LibraryMembership.library_id)
        )
        if lock:
            statement = statement.with_for_update(of=LibraryMembership)
        return list(self.session.scalars(statement))

    def active_library(self, library_id: UUID) -> Library | None:
        return self.session.scalar(
            select(Library).where(
                Library.id == library_id,
                Library.state == "active",
            )
        )

    def owner_user_ids(self, library_id: UUID) -> list[UUID]:
        return list(
            self.session.scalars(
                select(LibraryMembership.user_id)
                .where(
                    LibraryMembership.library_id == library_id,
                    LibraryMembership.role == "OWNER",
                )
                .order_by(LibraryMembership.created_at, LibraryMembership.id)
            )
        )

    def pending_tombstone(self, user_id: UUID, *, lock: bool = False) -> AccountDeletionTombstone | None:
        statement = select(AccountDeletionTombstone).where(
            AccountDeletionTombstone.user_id == user_id,
            AccountDeletionTombstone.state == "PENDING",
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def pending_tombstone_by_token_hash(
        self, token_hash: str, *, lock: bool = False
    ) -> AccountDeletionTombstone | None:
        statement = select(AccountDeletionTombstone).where(
            AccountDeletionTombstone.recovery_token_hash == token_hash,
            AccountDeletionTombstone.state == "PENDING",
        )
        if lock:
            statement = statement.with_for_update()
        return self.session.scalar(statement)

    def profile_image(self, user_id: UUID) -> UserProfileImage | None:
        return self.session.get(UserProfileImage, user_id)

    def add_tombstone(self, tombstone: AccountDeletionTombstone) -> None:
        self.session.add(tombstone)

    def delete_membership(self, membership: LibraryMembership) -> None:
        self.session.delete(membership)

    def add_membership(self, membership: LibraryMembership) -> None:
        self.session.add(membership)

    def commit_with_storage(self) -> None:
        from ..services.storage_transactions import commit_with_storage

        commit_with_storage(self.session)

    def rollback(self) -> None:
        self.session.rollback()
