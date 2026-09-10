"""Privacy-safe scheduled maintenance and service invariant checks."""

from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil

from sqlalchemy import delete, func, or_, select, text
from sqlalchemy.orm import Session

from .cover_storage import CoverStorage
from .models import (
    AccountActionToken,
    AccountDeletionTombstone,
    AccountInvitation,
    EmailOutboxMessage,
    LibraryImportJob,
    LibraryInvitation,
    LibraryDeletionTombstone,
    RateLimitBucket,
    SecurityEvent,
    UserSession,
)
from .private_object_operations import audit_private_objects, expected_private_objects
from .services.library_deletion_cleanup import (
    finalize_expired_account_deletions,
    finalize_expired_library_deletions,
)


@dataclass(frozen=True)
class MaintenanceResult:
    finalized_libraries: int = 0
    finalized_accounts: int = 0
    expired_imports: int = 0
    removed_import_records: int = 0
    removed_rate_buckets: int = 0
    removed_sessions: int = 0
    removed_action_tokens: int = 0
    removed_account_invitations: int = 0
    removed_library_invitations: int = 0
    removed_outbox_messages: int = 0
    removed_security_events: int = 0

    def payload(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class OperationsStatus:
    healthy: bool
    checks: dict[str, str]
    counters: dict[str, int]

    def payload(self) -> dict:
        return {"healthy": self.healthy, "checks": self.checks, "counters": self.counters}


def _safe_staging_path(root: Path, key: str) -> Path:
    resolved_root = root.resolve()
    candidate = (resolved_root / key).resolve()
    if resolved_root not in candidate.parents:
        raise RuntimeError("Import staging key escapes its root")
    return candidate


def run_maintenance(
    session: Session,
    storage: CoverStorage,
    staging_root: Path,
    *,
    now: datetime | None = None,
) -> MaintenanceResult:
    moment = now or datetime.now(UTC)
    finalized_libraries = finalize_expired_library_deletions(session, storage, now=moment)
    finalized_accounts = finalize_expired_account_deletions(session, storage, now=moment)

    expiring_jobs = list(
        session.scalars(
            select(LibraryImportJob)
            .where(
                or_(
                    (
                        LibraryImportJob.state.in_(("READY", "FAILED"))
                        & (LibraryImportJob.expires_at <= moment)
                    ),
                    (
                        (LibraryImportJob.state == "IMPORTING")
                        & (
                            LibraryImportJob.expires_at
                            <= moment - timedelta(hours=2)
                        )
                    ),
                )
            )
            .with_for_update(skip_locked=True)
        )
    )
    for job in expiring_jobs:
        job.state = "EXPIRED"
        shutil.rmtree(_safe_staging_path(staging_root, job.staging_key), ignore_errors=True)

    old_imports = list(
        session.scalars(
            select(LibraryImportJob).where(
                LibraryImportJob.expires_at <= moment - timedelta(days=7),
                LibraryImportJob.state.in_(("IMPORTED", "FAILED", "EXPIRED")),
            )
        )
    )
    for job in old_imports:
        shutil.rmtree(_safe_staging_path(staging_root, job.staging_key), ignore_errors=True)
        session.delete(job)

    removed_rate_buckets = session.execute(
        delete(RateLimitBucket).where(
            RateLimitBucket.updated_at <= moment - timedelta(days=2)
        )
    ).rowcount
    removed_sessions = session.execute(
        delete(UserSession).where(
            or_(
                UserSession.absolute_expires_at <= moment - timedelta(days=7),
                UserSession.revoked_at <= moment - timedelta(days=7),
            )
        )
    ).rowcount
    removed_action_tokens = session.execute(
        delete(AccountActionToken).where(
            AccountActionToken.expires_at <= moment - timedelta(days=30)
        )
    ).rowcount
    removed_account_invitations = session.execute(
        delete(AccountInvitation).where(
            AccountInvitation.expires_at <= moment - timedelta(days=30)
        )
    ).rowcount
    removed_library_invitations = session.execute(
        delete(LibraryInvitation).where(
            LibraryInvitation.expires_at <= moment - timedelta(days=30)
        )
    ).rowcount
    removed_outbox_messages = session.execute(
        delete(EmailOutboxMessage).where(
            or_(
                (
                    EmailOutboxMessage.state.in_(("SENT", "CANCELLED"))
                    & (EmailOutboxMessage.updated_at <= moment - timedelta(days=7))
                ),
                (
                    (EmailOutboxMessage.state == "FAILED")
                    & (EmailOutboxMessage.updated_at <= moment - timedelta(days=30))
                ),
            )
        )
    ).rowcount
    removed_security_events = session.execute(
        delete(SecurityEvent).where(
            SecurityEvent.occurred_at <= moment - timedelta(days=180)
        )
    ).rowcount
    session.commit()
    return MaintenanceResult(
        finalized_libraries=finalized_libraries,
        finalized_accounts=finalized_accounts,
        expired_imports=len(expiring_jobs),
        removed_import_records=len(old_imports),
        removed_rate_buckets=removed_rate_buckets or 0,
        removed_sessions=removed_sessions or 0,
        removed_action_tokens=removed_action_tokens or 0,
        removed_account_invitations=removed_account_invitations or 0,
        removed_library_invitations=removed_library_invitations or 0,
        removed_outbox_messages=removed_outbox_messages or 0,
        removed_security_events=removed_security_events or 0,
    )


def collect_operations_status(
    session: Session,
    storage: CoverStorage,
    *,
    deep: bool = False,
    now: datetime | None = None,
) -> OperationsStatus:
    moment = now or datetime.now(UTC)
    session.execute(text("SELECT 1"))
    counters = {
        "email_failed": int(
            session.scalar(
                select(func.count()).select_from(EmailOutboxMessage).where(
                    EmailOutboxMessage.state == "FAILED"
                )
            )
            or 0
        ),
        "email_overdue": int(
            session.scalar(
                select(func.count()).select_from(EmailOutboxMessage).where(
                    EmailOutboxMessage.state.in_(("PENDING", "PROCESSING")),
                    EmailOutboxMessage.created_at <= moment - timedelta(minutes=15),
                )
            )
            or 0
        ),
        "account_deletions_overdue": int(
            session.scalar(
                select(func.count()).select_from(AccountDeletionTombstone).where(
                    AccountDeletionTombstone.state == "PENDING",
                    AccountDeletionTombstone.recover_until <= moment,
                )
            )
            or 0
        ),
        "library_deletions_overdue": int(
            session.scalar(
                select(func.count()).select_from(LibraryDeletionTombstone).where(
                    LibraryDeletionTombstone.state == "PENDING",
                    LibraryDeletionTombstone.recover_until <= moment,
                )
            )
            or 0
        ),
    }
    checks = {
        "database": "ready",
        "email_outbox": (
            "ready"
            if not counters["email_failed"] and not counters["email_overdue"]
            else "attention"
        ),
        "deletion_cleanup": (
            "ready"
            if not counters["account_deletions_overdue"]
            and not counters["library_deletions_overdue"]
            else "attention"
        ),
    }
    if deep:
        audit = audit_private_objects(
            expected_private_objects(session), storage.iter_objects()
        )
        counters.update(
            {
                "private_objects_expected": audit.expected_count,
                "private_objects_stored": audit.stored_count,
                "private_objects_missing": len(audit.missing),
                "private_objects_orphaned": len(audit.orphaned),
                "private_objects_mismatched": len(audit.mismatched),
            }
        )
        checks["private_objects"] = "ready" if audit.is_exact else "attention"
    return OperationsStatus(
        healthy=all(value == "ready" for value in checks.values()),
        checks=checks,
        counters=counters,
    )
