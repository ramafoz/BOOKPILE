from uuid import UUID

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..models import (
    Library,
    LibraryAuditEvent,
    LibraryInvitation,
    LibraryMembership,
    LibraryDeletionTombstone,
    LibraryStorageAllocation,
    LibraryStorageUsage,
    BookCover,
    User,
)


class LibraryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def lock_storage_entitlements_first(self) -> None:
        """Establish the global quota lock order before membership row locks."""
        from .storage import StorageRepository

        StorageRepository(self._session).ensure_entitlements()

    def find_membership(
        self, *, library_id: UUID, user_id: UUID
    ) -> LibraryMembership | None:
        return self._session.scalar(
            select(LibraryMembership)
            .join(LibraryMembership.library)
            .options(
                joinedload(LibraryMembership.library),
                joinedload(LibraryMembership.user),
                joinedload(LibraryMembership.selected_reading_user),
            )
            .where(
                LibraryMembership.library_id == library_id,
                LibraryMembership.user_id == user_id,
                Library.state == "active",
            )
        )

    def list_memberships_for_user(self, user_id: UUID) -> list[LibraryMembership]:
        return list(
            self._session.scalars(
                select(LibraryMembership)
                .join(LibraryMembership.library)
                .options(joinedload(LibraryMembership.library))
                .where(
                    LibraryMembership.user_id == user_id,
                    Library.state == "active",
                )
                .order_by(Library.name, Library.id)
            )
        )

    def list_members_for_library(self, library_id: UUID) -> list[LibraryMembership]:
        return list(
            self._session.scalars(
                select(LibraryMembership)
                .options(joinedload(LibraryMembership.user))
                .where(LibraryMembership.library_id == library_id)
                .order_by(LibraryMembership.created_at, LibraryMembership.id)
            )
        )

    def lock_members_for_library(self, library_id: UUID) -> list[LibraryMembership]:
        return list(
            self._session.scalars(
                select(LibraryMembership)
                .where(LibraryMembership.library_id == library_id)
                .order_by(LibraryMembership.id)
                .with_for_update()
            )
        )

    def find_user(self, user_id: UUID) -> User | None:
        return self._session.get(User, user_id)

    def lock_library(self, library_id: UUID) -> Library | None:
        return self._session.scalar(
            select(Library).where(Library.id == library_id).with_for_update()
        )

    def allocations_for_library(self, library_id: UUID) -> list[LibraryStorageAllocation]:
        return list(
            self._session.scalars(
                select(LibraryStorageAllocation)
                .where(LibraryStorageAllocation.library_id == library_id)
                .order_by(LibraryStorageAllocation.user_id)
            )
        )

    def usage_for_library(self, library_id: UUID) -> LibraryStorageUsage | None:
        return self._session.get(LibraryStorageUsage, library_id)

    def cover_manifest(self, library_id: UUID) -> list[BookCover]:
        return list(
            self._session.scalars(
                select(BookCover)
                .where(BookCover.library_id == library_id)
                .order_by(BookCover.book_id)
            )
        )

    def add_tombstone(self, tombstone: LibraryDeletionTombstone) -> None:
        self._session.add(tombstone)

    def lock_tombstone(self, tombstone_id: UUID) -> LibraryDeletionTombstone | None:
        return self._session.scalar(
            select(LibraryDeletionTombstone)
            .where(LibraryDeletionTombstone.id == tombstone_id)
            .with_for_update()
        )

    def recoverable_tombstones(self, user_id: UUID) -> list[LibraryDeletionTombstone]:
        user = str(user_id)
        return [
            item
            for item in self._session.scalars(
                select(LibraryDeletionTombstone)
                .where(LibraryDeletionTombstone.state == "PENDING")
                .order_by(LibraryDeletionTombstone.recover_until)
            )
            if any(
                member.get("user_id") == user and member.get("role") == "OWNER"
                for member in item.membership_snapshot
            )
        ]

    def revoke_open_invitations(self, *, library_id: UUID, now: datetime) -> None:
        invitations = self._session.scalars(
            select(LibraryInvitation).where(
                LibraryInvitation.library_id == library_id,
                LibraryInvitation.consumed_at.is_(None),
                LibraryInvitation.revoked_at.is_(None),
            )
        )
        for invitation in invitations:
            invitation.revoked_at = now

    def find_user_by_username(self, username: str) -> User | None:
        return self._session.scalar(
            select(User).where(User.username == username.strip().lower())
        )

    def slug_exists(self, slug: str) -> bool:
        return bool(
            self._session.scalar(
                select(func.count()).select_from(Library).where(Library.slug == slug)
            )
        )

    def add_library(self, library: Library) -> None:
        self._session.add(library)

    def add_membership(self, membership: LibraryMembership) -> None:
        self._session.add(membership)

    def delete_membership(self, membership: LibraryMembership) -> None:
        self._session.delete(membership)

    def add_invitation(self, invitation: LibraryInvitation) -> None:
        self._session.add(invitation)

    def find_invitation_for_update(
        self, token_hash: str
    ) -> LibraryInvitation | None:
        return self._session.scalar(
            select(LibraryInvitation)
            .options(selectinload(LibraryInvitation.library))
            .where(LibraryInvitation.token_hash == token_hash)
            .with_for_update(of=LibraryInvitation)
        )

    def find_invitation(self, invitation_id: UUID) -> LibraryInvitation | None:
        return self._session.get(LibraryInvitation, invitation_id)

    def revoke_open_invitations_by_creator(
        self, *, library_id: UUID, creator_user_id: UUID, now: datetime
    ) -> None:
        invitations = self._session.scalars(
            select(LibraryInvitation).where(
                LibraryInvitation.library_id == library_id,
                LibraryInvitation.created_by_user_id == creator_user_id,
                LibraryInvitation.consumed_at.is_(None),
                LibraryInvitation.revoked_at.is_(None),
            )
        )
        for invitation in invitations:
            invitation.revoked_at = now

    def add_audit_event(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID | None,
        event_type: str,
        details: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            LibraryAuditEvent(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                details=details or {},
            )
        )

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        from ..services.storage_transactions import commit_with_storage

        commit_with_storage(self._session)

    def rollback(self) -> None:
        self._session.rollback()
