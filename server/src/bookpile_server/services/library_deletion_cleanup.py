"""Final cleanup for shared libraries whose recovery window has elapsed."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cover_storage import CoverStorage
from ..models import Library, LibraryDeletionTombstone


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
