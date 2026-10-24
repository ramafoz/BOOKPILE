"""Fail-closed recovery of abandoned private objects."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
import hashlib
import hmac

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from .cover_storage import CoverStorage, StoredObjectInfo
from .models import (
    BookCover,
    LibraryImportJob,
    OperationLease,
    SecurityEvent,
    UserProfileImage,
)
from .private_object_operations import expected_private_objects


PROTECTED_LEASE_SCOPES = (
    "portable_export_user",
    "portable_export_library",
    "import_consolidation_user",
    "import_consolidation_library",
)
IN_FLIGHT_IMPORT_STATES = ("READY", "IMPORTING")


@dataclass(frozen=True)
class OrphanRecoveryResult:
    mode: str
    expected_count: int
    stored_count: int
    orphaned_count: int
    too_young_count: int
    unknown_age_count: int
    protected_count: int
    candidate_count: int
    candidates: tuple[str, ...]
    deleted_count: int
    deleted: tuple[str, ...]
    active_leases: int
    in_flight_jobs: int
    grace_hours: int
    max_deletions: int

    def payload(self) -> dict[str, object]:
        return asdict(self)


def fingerprint_private_object_key(secret: str, object_key: str) -> str:
    return hmac.new(
        secret.encode("utf-8"), object_key.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _database_now(session: Session) -> datetime:
    dialect = session.get_bind().dialect.name
    expression = (
        func.clock_timestamp() if dialect == "postgresql" else func.datetime("now")
    )
    value = session.scalar(select(expression))
    if value is None:
        raise RuntimeError("Database clock is unavailable")
    if isinstance(value, str):
        value = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value


def _active_work(session: Session, now: datetime) -> tuple[int, int]:
    active_leases = int(
        session.scalar(
            select(func.count()).select_from(OperationLease).where(
                OperationLease.scope.in_(PROTECTED_LEASE_SCOPES),
                OperationLease.released_at.is_(None),
                OperationLease.expires_at > now,
            )
        )
        or 0
    )
    in_flight_jobs = int(
        session.scalar(
            select(func.count()).select_from(LibraryImportJob).where(
                LibraryImportJob.state.in_(IN_FLIGHT_IMPORT_STATES)
            )
        )
        or 0
    )
    return active_leases, in_flight_jobs


def _lock_cleanup_decisions(session: Session) -> None:
    if session.get_bind().dialect.name != "postgresql":
        return
    # SHARE conflicts with the ROW EXCLUSIVE lock taken by INSERT/UPDATE/DELETE.
    # Hold these locks through the external delete and completion-event commit so
    # no protected work or metadata reference can appear after the final checks.
    session.execute(
        text(
            "LOCK TABLE operation_leases, library_import_jobs, book_covers, "
            "user_profile_images IN SHARE MODE"
        )
    )


def _is_referenced(session: Session, object_key: str) -> bool:
    cover = session.scalar(
        select(BookCover.object_key).where(BookCover.object_key == object_key).limit(1)
    )
    if cover is not None:
        return True
    profile = session.scalar(
        select(UserProfileImage.object_key)
        .where(UserProfileImage.object_key == object_key)
        .limit(1)
    )
    return profile is not None


def _same_object(left: StoredObjectInfo, right: StoredObjectInfo) -> bool:
    return (
        left.object_key == right.object_key
        and left.byte_size == right.byte_size
        and left.sha256 == right.sha256
        and left.last_modified == right.last_modified
    )


def recover_abandoned_private_objects(
    session: Session,
    storage: CoverStorage,
    *,
    key_secret: str,
    deployment_revision: str,
    grace: timedelta,
    max_deletions: int,
    apply: bool,
) -> OrphanRecoveryResult:
    if grace <= timedelta(0):
        raise ValueError("Private-object orphan grace must be positive")
    if max_deletions < 1:
        raise ValueError("Private-object deletion limit must be positive")
    if not key_secret:
        raise ValueError("Private-object recovery requires a fingerprint secret")

    now = _database_now(session)
    cutoff = now - grace
    expected = expected_private_objects(session)
    expected_keys = {item.object_key for item in expected}
    stored = list(storage.iter_objects())
    orphans = [item for item in stored if item.object_key not in expected_keys]
    too_young = [
        item
        for item in orphans
        if item.last_modified is not None and item.last_modified > cutoff
    ]
    unknown_age = [item for item in orphans if item.last_modified is None]
    old = [
        item
        for item in orphans
        if item.last_modified is not None and item.last_modified <= cutoff
    ]
    active_leases, in_flight_jobs = _active_work(session, now)
    protected_count = len(old) if active_leases or in_flight_jobs else 0
    eligible = (
        []
        if protected_count
        else sorted(
            old, key=lambda item: (item.last_modified or now, item.object_key)
        )
    )
    selected = eligible[:max_deletions]
    candidate_fingerprints = tuple(
        fingerprint_private_object_key(key_secret, item.object_key) for item in selected
    )
    deleted: list[str] = []

    if apply:
        for planned in selected:
            check_now = _database_now(session)
            current_leases, current_jobs = _active_work(session, check_now)
            if current_leases or current_jobs:
                raise RuntimeError(
                    "Private-object cleanup stopped because protected work became active"
                )
            if _is_referenced(session, planned.object_key):
                raise RuntimeError(
                    "Private-object cleanup stopped because a candidate became referenced"
                )
            current = storage.stat(planned.object_key)
            if current is None:
                continue
            if not _same_object(current, planned):
                raise RuntimeError(
                    "Private-object cleanup stopped because a candidate changed"
                )
            if (
                current.last_modified is None
                or current.last_modified > check_now - grace
            ):
                raise RuntimeError(
                    "Private-object cleanup stopped because candidate age is unsafe"
                )
            fingerprint = fingerprint_private_object_key(key_secret, current.object_key)
            session.add(
                SecurityEvent(
                    event_type="private_object_orphan_deletion_authorized",
                    ip_address=None,
                    details={
                        "object_key_hmac": fingerprint,
                        "byte_size": current.byte_size,
                        "deployment_revision": deployment_revision,
                    },
                )
            )
            session.commit()
            _lock_cleanup_decisions(session)
            delete_now = _database_now(session)
            delete_leases, delete_jobs = _active_work(session, delete_now)
            if delete_leases or delete_jobs:
                raise RuntimeError(
                    "Private-object cleanup stopped because protected work became active"
                )
            if _is_referenced(session, current.object_key):
                raise RuntimeError(
                    "Private-object cleanup stopped because a candidate became referenced"
                )
            delete_candidate = storage.stat(current.object_key)
            if delete_candidate is None:
                session.rollback()
                continue
            if not _same_object(delete_candidate, current):
                raise RuntimeError(
                    "Private-object cleanup stopped because a candidate changed"
                )
            if (
                delete_candidate.last_modified is None
                or delete_candidate.last_modified > delete_now - grace
            ):
                raise RuntimeError(
                    "Private-object cleanup stopped because candidate age is unsafe"
                )
            storage.delete(delete_candidate.object_key)
            if storage.stat(delete_candidate.object_key) is not None:
                raise RuntimeError("Private-object deletion verification failed")
            session.add(
                SecurityEvent(
                    event_type="private_object_orphan_deleted",
                    ip_address=None,
                    details={
                        "object_key_hmac": fingerprint,
                        "byte_size": current.byte_size,
                        "deployment_revision": deployment_revision,
                    },
                )
            )
            session.commit()
            deleted.append(fingerprint)

    return OrphanRecoveryResult(
        mode="apply" if apply else "dry-run",
        expected_count=len(expected),
        stored_count=len(stored),
        orphaned_count=len(orphans),
        too_young_count=len(too_young),
        unknown_age_count=len(unknown_age),
        protected_count=protected_count,
        candidate_count=len(selected),
        candidates=candidate_fingerprints,
        deleted_count=len(deleted),
        deleted=tuple(deleted),
        active_leases=active_leases,
        in_flight_jobs=in_flight_jobs,
        grace_hours=int(grace.total_seconds() // 3600),
        max_deletions=max_deletions,
    )
