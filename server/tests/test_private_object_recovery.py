from contextlib import nullcontext
from datetime import UTC, datetime, timedelta
import json
import os
import sys
from uuid import uuid4

import pytest
from sqlalchemy import select

from bookpile_server.cli import private_objects as private_objects_cli
from bookpile_server.config import Settings
from bookpile_server.cover_storage import FilesystemCoverStorage, StoredObjectInfo
from bookpile_server.models import (
    Library,
    LibraryImportJob,
    OperationLease,
    SecurityEvent,
    User,
)
from bookpile_server.private_object_recovery import (
    recover_abandoned_private_objects,
)
from bookpile_server.private_object_operations import ExpectedPrivateObject


SECRET = "private-object-recovery-test-secret"


def _old_object(storage: FilesystemCoverStorage, root, key: str) -> None:
    storage.put(key, b"abandoned")
    old = (datetime.now(UTC) - timedelta(hours=48)).timestamp()
    path = root / key
    os.utime(path, (old, old))


def _recover(session, storage, *, apply: bool, limit: int = 25):
    return recover_abandoned_private_objects(
        session,
        storage,
        key_secret=SECRET,
        deployment_revision="git-recovery-test",
        grace=timedelta(hours=24),
        max_deletions=limit,
        apply=apply,
    )


def test_dry_run_lists_only_old_unreferenced_objects_with_hmac(session, tmp_path) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    _old_object(storage, root, "covers/old-orphan.webp")
    storage.put("covers/young-orphan.webp", b"young")

    result = _recover(session, storage, apply=False)

    assert result.orphaned_count == 2
    assert result.too_young_count == 1
    assert result.unknown_age_count == 0
    assert result.candidate_count == 1
    assert len(result.candidates[0]) == 64
    assert "old-orphan" not in str(result.payload())
    assert storage.stat("covers/old-orphan.webp") is not None


def test_referenced_object_is_never_a_candidate(
    session, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    object_key = "covers/expected.webp"
    _old_object(storage, root, object_key)
    info = storage.stat(object_key)
    assert info is not None and info.sha256 is not None
    monkeypatch.setattr(
        "bookpile_server.private_object_recovery.expected_private_objects",
        lambda _session: [
            ExpectedPrivateObject(object_key, info.byte_size, info.sha256)
        ],
    )

    result = _recover(session, storage, apply=True)

    assert result.expected_count == 1
    assert result.orphaned_count == 0
    assert result.candidate_count == 0
    assert result.deleted_count == 0
    assert storage.stat(object_key) is not None


def test_apply_is_bounded_deletes_exact_objects_and_audits_each_one(
    session, tmp_path
) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    _old_object(storage, root, "covers/first.webp")
    _old_object(storage, root, "covers/second.webp")

    result = _recover(session, storage, apply=True, limit=1)

    assert result.candidate_count == 1
    assert result.deleted_count == 1
    assert len(list(storage.iter_objects())) == 1
    events = list(
        session.scalars(
            select(SecurityEvent).order_by(SecurityEvent.id)
        )
    )
    assert [event.event_type for event in events] == [
        "private_object_orphan_deletion_authorized",
        "private_object_orphan_deleted",
    ]
    assert events[0].details["object_key_hmac"] == result.deleted[0]
    assert events[1].details["object_key_hmac"] == result.deleted[0]
    assert "covers/" not in str([event.details for event in events])


def test_active_operation_lease_protects_every_old_orphan(session, tmp_path) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    _old_object(storage, root, "covers/protected.webp")
    now = datetime.now(UTC)
    session.add(
        OperationLease(
            scope="portable_export_library",
            key_hash="a" * 64,
            lease_id=uuid4(),
            fencing_token=1,
            acquired_at=now,
            renewed_at=now,
            expires_at=now + timedelta(minutes=5),
            released_at=None,
        )
    )
    session.commit()

    result = _recover(session, storage, apply=True)

    assert result.active_leases == 1
    assert result.protected_count == 1
    assert result.candidate_count == 0
    assert result.deleted_count == 0
    assert storage.stat("covers/protected.webp") is not None


def test_in_flight_import_job_protects_every_old_orphan(session, tmp_path) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    _old_object(storage, root, "covers/import-protected.webp")
    now = datetime.now(UTC)
    user = User(
        email="recovery@example.test",
        username="recovery",
        password_hash="x",
        state="active",
    )
    session.add(user)
    session.flush()
    library = Library(name="Recovery", slug="recovery", created_by_user_id=user.id)
    session.add(library)
    session.flush()
    session.add(
        LibraryImportJob(
            library_id=library.id,
            created_by_user_id=user.id,
            state="READY",
            adapter="test",
            backup_format_version=1,
            local_schema_version=1,
            source_created_at=now.isoformat(),
            archive_sha256="a" * 64,
            source_fingerprint="b" * 64,
            staging_sha256="c" * 64,
            staging_key=uuid4().hex,
            source_counts={},
            source_kind="LOCAL",
            source_members=[],
            warnings=[],
            archive_bytes=1,
            uncompressed_bytes=1,
            estimated_logical_bytes=1,
            capacity_available=True,
            expires_at=now + timedelta(hours=1),
        )
    )
    session.commit()

    result = _recover(session, storage, apply=True)

    assert result.in_flight_jobs == 1
    assert result.protected_count == 1
    assert result.deleted_count == 0
    assert storage.stat("covers/import-protected.webp") is not None


def test_database_or_lease_decision_failure_stops_before_deletion(
    session, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    _old_object(storage, root, "covers/fail-closed.webp")

    def unavailable(*_args, **_kwargs):
        raise RuntimeError("database unavailable")

    monkeypatch.setattr(
        "bookpile_server.private_object_recovery._active_work", unavailable
    )

    with pytest.raises(RuntimeError, match="database unavailable"):
        _recover(session, storage, apply=True)

    assert storage.stat("covers/fail-closed.webp") is not None


def test_candidate_change_after_authorization_stops_exact_delete(
    session, tmp_path, monkeypatch
) -> None:
    root = tmp_path / "objects"
    storage = FilesystemCoverStorage(root)
    object_key = "covers/racing.webp"
    _old_object(storage, root, object_key)
    original_stat = storage.stat
    calls = 0

    def changing_stat(key: str):
        nonlocal calls
        calls += 1
        if calls == 2:
            storage.put(key, b"replacement")
        return original_stat(key)

    monkeypatch.setattr(storage, "stat", changing_stat)

    with pytest.raises(RuntimeError, match="candidate changed"):
        _recover(session, storage, apply=True)

    assert storage.read(object_key) == b"replacement"
    events = list(session.scalars(select(SecurityEvent).order_by(SecurityEvent.id)))
    assert [event.event_type for event in events] == [
        "private_object_orphan_deletion_authorized"
    ]


def test_unknown_provider_age_fails_closed(session) -> None:
    class UnknownAgeStorage:
        deleted = False

        def iter_objects(self):
            yield StoredObjectInfo("covers/unknown.webp", 7, "a" * 64, None)

        def delete(self, _object_key):
            self.deleted = True

    storage = UnknownAgeStorage()

    result = _recover(session, storage, apply=True)  # type: ignore[arg-type]

    assert result.unknown_age_count == 1
    assert result.candidate_count == 0
    assert result.deleted_count == 0
    assert storage.deleted is False


def test_staging_rehearsal_injection_is_audited_and_prints_only_hmac(
    session, tmp_path, monkeypatch, capsys
) -> None:
    storage = FilesystemCoverStorage(tmp_path / "objects")
    settings = Settings(
        environment="test",
        deployment_revision="git-injection-test",
        rate_limit_key_secret=SECRET,
    ).model_copy(update={"environment": "staging"})
    monkeypatch.setattr(private_objects_cli, "get_settings", lambda: settings)
    monkeypatch.setattr(
        private_objects_cli, "get_private_object_storage", lambda: storage
    )
    monkeypatch.setattr(
        private_objects_cli, "SessionFactory", lambda: nullcontext(session)
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "bookpile-private-objects",
            "inject-orphan-rehearsal",
            "--confirm",
            "STAGING-ORPHAN-REHEARSAL",
        ],
    )

    assert private_objects_cli.main() == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["created"] is True
    assert len(payload["object_key_hmac"]) == 64
    stored = list(storage.iter_objects())
    assert len(stored) == 1
    assert stored[0].object_key not in str(payload)
    event = session.scalar(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "private_object_orphan_rehearsal_created"
        )
    )
    assert event is not None
    assert event.details["object_key_hmac"] == payload["object_key_hmac"]
    assert stored[0].object_key not in str(event.details)


@pytest.mark.parametrize(
    ("mode", "confirmation"),
    (
        ("off", "DELETE-ABANDONED-PRIVATE-OBJECTS"),
        ("enforce", None),
    ),
)
def test_manual_apply_requires_enforce_mode_and_explicit_confirmation(
    session, tmp_path, monkeypatch, mode: str, confirmation: str | None
) -> None:
    storage = FilesystemCoverStorage(tmp_path / "objects")
    settings = Settings(
        environment="test",
        deployment_revision="git-apply-gate-test",
        rate_limit_key_secret=SECRET,
    ).model_copy(
        update={
            "environment": "staging",
            "private_object_orphan_cleanup_mode": mode,
        }
    )
    monkeypatch.setattr(private_objects_cli, "get_settings", lambda: settings)
    monkeypatch.setattr(
        private_objects_cli, "get_private_object_storage", lambda: storage
    )
    monkeypatch.setattr(
        private_objects_cli, "SessionFactory", lambda: nullcontext(session)
    )
    arguments = [
        "bookpile-private-objects",
        "recover-orphans",
        "--apply",
    ]
    if confirmation is not None:
        arguments.extend(("--confirm", confirmation))
    monkeypatch.setattr(sys, "argv", arguments)

    with pytest.raises(SystemExit) as raised:
        private_objects_cli.main()

    assert raised.value.code == 2
    assert list(storage.iter_objects()) == []
