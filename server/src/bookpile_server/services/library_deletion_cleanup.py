"""Final cleanup for shared libraries whose recovery window has elapsed."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..cover_storage import CoverStorage
from ..models import (
    AccountDeletionTombstone,
    EmailOutboxMessage,
    Library,
    LibraryDeletionTombstone,
    User,
)


TOMBSTONE_RETENTION = timedelta(days=30)


def finalize_expired_library_deletions(
    session: Session,
    storage: CoverStorage,
    *,
    now: datetime | None = None,
) -> int:
    """Delete quarantined data/objects and retain only a short audit tombstone."""

    moment = now or datetime.now(UTC)
    pending = list(
        session.scalars(
            select(LibraryDeletionTombstone)
            .where(
                LibraryDeletionTombstone.state == "PENDING",
                LibraryDeletionTombstone.recover_until <= moment,
            )
            .order_by(LibraryDeletionTombstone.recover_until)
            .with_for_update(skip_locked=True)
        )
    )
    finalized = 0
    for tombstone in pending:
        for item in tombstone.object_manifest:
            object_key = item.get("object_key")
            if isinstance(object_key, str):
                storage.delete(object_key)
        library = session.get(Library, tombstone.library_id)
        if library is not None:
            session.delete(library)
        tombstone.state = "FINALIZED"
        tombstone.finalized_at = moment
        finalized += 1

    expired_tombstones = list(
        session.scalars(
            select(LibraryDeletionTombstone).where(
                LibraryDeletionTombstone.state == "FINALIZED",
                LibraryDeletionTombstone.finalized_at <= moment - TOMBSTONE_RETENTION,
            )
        )
    )
    for tombstone in expired_tombstones:
        session.delete(tombstone)
    session.commit()
    return finalized


def finalize_expired_account_deletions(
    session: Session,
    storage: CoverStorage,
    *,
    now: datetime | None = None,
) -> int:
    """Erase expired accounts and their profile objects, then anonymize tombstones."""

    moment = now or datetime.now(UTC)
    recovery_email_exists = (
        select(EmailOutboxMessage.id)
        .where(
            EmailOutboxMessage.account_deletion_tombstone_id
            == AccountDeletionTombstone.id
        )
        .exists()
    )
    recovery_email_sent = (
        select(EmailOutboxMessage.id)
        .where(
            EmailOutboxMessage.account_deletion_tombstone_id
            == AccountDeletionTombstone.id,
            EmailOutboxMessage.state == "SENT",
        )
        .exists()
    )
    pending = list(
        session.scalars(
            select(AccountDeletionTombstone)
            .where(
                AccountDeletionTombstone.state == "PENDING",
                AccountDeletionTombstone.recover_until <= moment,
                or_(~recovery_email_exists, recovery_email_sent),
            )
            .order_by(AccountDeletionTombstone.recover_until)
            .with_for_update(skip_locked=True)
        )
    )
    finalized = 0
    for tombstone in pending:
        for item in tombstone.object_manifest:
            object_key = item.get("object_key")
            if isinstance(object_key, str):
                storage.delete(object_key)
        user = session.get(User, tombstone.user_id)
        if user is not None:
            session.delete(user)
        tombstone.username = None
        tombstone.email = None
        tombstone.membership_snapshot = []
        tombstone.object_manifest = []
        tombstone.recovery_token_hash = None
        tombstone.state = "FINALIZED"
        tombstone.finalized_at = moment
        finalized += 1

    old = list(
        session.scalars(
            select(AccountDeletionTombstone).where(
                AccountDeletionTombstone.state == "FINALIZED",
                AccountDeletionTombstone.finalized_at <= moment - TOMBSTONE_RETENTION,
            )
        )
    )
    for tombstone in old:
        session.delete(tombstone)
    session.commit()
    return finalized
