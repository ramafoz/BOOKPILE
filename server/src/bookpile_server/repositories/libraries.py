from uuid import UUID

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload, selectinload

from ..models import (
    Library,
    LibraryAuditEvent,
    LibraryInvitation,
    LibraryMembership,
    User,
)


class LibraryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

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
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
