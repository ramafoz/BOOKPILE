from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.models import (
    EmailOutboxMessage,
    Library,
    LibraryImportJob,
    RateLimitBucket,
    SecurityEvent,
    User,
    UserSession,
)
from bookpile_server.operations import collect_operations_status, run_maintenance


def test_light_status_flags_failed_and_overdue_email_without_private_data(session, tmp_path) -> None:
    now = datetime.now(UTC)
    session.add_all(
        [
            EmailOutboxMessage(
                message_key="failed",
                purpose="PASSWORD_RESET",
                payload_ciphertext=b"encrypted",
                state="FAILED",
                available_at=now,
                updated_at=now,
            ),
            EmailOutboxMessage(
                message_key="overdue",
                purpose="EMAIL_VERIFICATION",
                payload_ciphertext=b"encrypted",
                state="PENDING",
                available_at=now - timedelta(hours=1),
                created_at=now - timedelta(hours=1),
                updated_at=now - timedelta(hours=1),
            ),
        ]
    )
    session.commit()

    status = collect_operations_status(
        session, FilesystemCoverStorage(tmp_path / "objects"), now=now
    )

    assert status.healthy is False
    assert status.checks["email_outbox"] == "attention"
    assert status.counters["email_failed"] == 1
    assert status.counters["email_overdue"] == 1
    assert "recipient" not in str(status.payload()).lower()


def test_deep_status_detects_orphaned_private_object(session, tmp_path) -> None:
    storage = FilesystemCoverStorage(tmp_path / "objects")
    storage.put("orphan.webp", b"orphan")

    status = collect_operations_status(session, storage, deep=True)

    assert status.healthy is False
    assert status.checks["private_objects"] == "attention"
    assert status.counters["private_objects_orphaned"] == 1


def test_maintenance_prunes_only_records_beyond_retention(session, tmp_path) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=200)
    user = User(
        email="maintenance@example.test",
        username="maintenance",
        password_hash="x",
        state="active",
    )
    session.add(user)
    session.flush()
    session.add_all(
        [
            RateLimitBucket(
                scope="login",
                key_hash="old",
                window_started_at=old,
                attempt_count=1,
                updated_at=old,
            ),
            RateLimitBucket(
                scope="login",
                key_hash="current",
                window_started_at=now,
                attempt_count=1,
                updated_at=now,
            ),
            UserSession(
                user_id=user.id,
                token_hash=uuid4().hex,
                csrf_token_hash=uuid4().hex,
                remember_me=False,
                last_seen_at=old,
                expires_at=old,
                absolute_expires_at=old,
            ),
            SecurityEvent(event_type="old", occurred_at=old, details={}),
            EmailOutboxMessage(
                message_key="sent-old",
                purpose="PASSWORD_RESET",
                payload_ciphertext=b"encrypted",
                state="SENT",
                available_at=old,
                sent_at=old,
                updated_at=old,
            ),
        ]
    )
    session.commit()

    result = run_maintenance(
        session,
        FilesystemCoverStorage(tmp_path / "objects"),
        tmp_path / "staging",
        now=now,
    )

    assert result.removed_rate_buckets == 1
    assert result.removed_sessions == 1
    assert result.removed_security_events == 1
    assert result.removed_outbox_messages == 1
    assert session.scalar(select(RateLimitBucket.key_hash)) == "current"


def test_maintenance_does_not_expire_recently_running_import(session, tmp_path) -> None:
    now = datetime.now(UTC)
    user = User(
        email="import-maintenance@example.test",
        username="import_maintenance",
        password_hash="x",
        state="active",
    )
    session.add(user)
    session.flush()
    library = Library(name="Import", slug="import-maintenance", created_by_user_id=user.id)
    session.add(library)
    session.flush()

    def job(key: str, expires_at: datetime) -> LibraryImportJob:
        return LibraryImportJob(
            library_id=library.id,
            created_by_user_id=user.id,
            state="IMPORTING",
            adapter="test",
            backup_format_version=1,
            local_schema_version=1,
            source_created_at=now.isoformat(),
            archive_sha256=("a" if key == "recent" else "b") * 64,
            source_fingerprint=("c" if key == "recent" else "d") * 64,
            staging_sha256=("e" if key == "recent" else "f") * 64,
            staging_key=key,
            source_counts={},
            source_kind="LOCAL",
            warnings=[],
            archive_bytes=1,
            uncompressed_bytes=1,
            estimated_logical_bytes=1,
            capacity_available=True,
            expires_at=expires_at,
        )

    recent = job("recent", now - timedelta(hours=1))
    abandoned = job("abandoned", now - timedelta(hours=3))
    session.add_all([recent, abandoned])
    session.commit()

    result = run_maintenance(
        session,
        FilesystemCoverStorage(tmp_path / "objects"),
        tmp_path / "staging",
        now=now,
    )

    session.refresh(recent)
    session.refresh(abandoned)
    assert result.expired_imports == 1
    assert recent.state == "IMPORTING"
    assert abandoned.state == "EXPIRED"
