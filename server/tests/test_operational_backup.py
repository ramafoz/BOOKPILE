from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import pytest

from bookpile_server.backup_crypto import BackupIntegrityError, decrypt_file, encrypt_file
from bookpile_server.backup_repository import S3BackupRepository
from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.operational_backup import OperationalBackupService, PostgresTools
from bookpile_server.private_object_operations import ExpectedPrivateObject


class MemoryRepository:
    def __init__(self) -> None:
        self.items: dict[str, bytes] = {}

    def put_file(self, key: str, source: Path, *, sha256: str) -> None:
        content = source.read_bytes()
        assert __import__("hashlib").sha256(content).hexdigest() == sha256
        self.items[key] = content

    def get_file(self, key: str, target: Path, *, sha256: str) -> None:
        content = self.items[key]
        if __import__("hashlib").sha256(content).hexdigest() != sha256:
            raise OSError("corrupt")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)

    def put_bytes(self, key: str, content: bytes) -> None:
        self.items[key] = content

    def get_bytes(self, key: str) -> bytes:
        return self.items[key]

    def list_keys(self, prefix: str) -> list[str]:
        return sorted(key for key in self.items if key.startswith(prefix))

    def delete_keys(self, keys: list[str]) -> None:
        for key in keys:
            self.items.pop(key, None)


class Body:
    def __init__(self, content: bytes) -> None:
        from io import BytesIO
        self.stream = BytesIO(content)
    def read(self) -> bytes:
        return self.stream.read()
    def close(self) -> None:
        self.stream.close()


class FakeS3:
    def __init__(self) -> None:
        self.items: dict[str, tuple[bytes, dict[str, str]]] = {}
        self.last_upload_args: dict = {}
    def upload_fileobj(self, stream, bucket, key, ExtraArgs) -> None:
        self.last_upload_args = ExtraArgs
        self.items[key] = (stream.read(), ExtraArgs["Metadata"])
    def download_fileobj(self, bucket, key, stream) -> None:
        stream.write(self.items[key][0])
    def head_object(self, Bucket, Key):
        content, metadata = self.items[Key]
        return {"ContentLength": len(content), "Metadata": metadata}
    def put_object(self, Bucket, Key, Body, Metadata, **kwargs):
        self.items[Key] = (Body, Metadata)
    def get_object(self, Bucket, Key):
        content, metadata = self.items[Key]
        return {"Body": Body(content), "Metadata": metadata}
    def delete_object(self, Bucket, Key):
        self.items.pop(Key, None)
    def head_bucket(self, Bucket):
        return {}
    def get_bucket_versioning(self, Bucket):
        return {"Status": "Enabled"}
    def get_object_lock_configuration(self, Bucket):
        return {"ObjectLockConfiguration": {"ObjectLockEnabled": "Enabled"}}


def object_entry(key: str, content: bytes) -> ExpectedPrivateObject:
    return ExpectedPrivateObject(key, len(content), sha256(content).hexdigest())


def create_snapshot(tmp_path: Path, *, now: datetime | None = None):
    repository = MemoryRepository()
    source = FilesystemCoverStorage(tmp_path / "source")
    source.put("covers/a.webp", b"cover-a")
    source.put("profiles/b.webp", b"profile-b")
    expected = [object_entry("covers/a.webp", b"cover-a"), object_entry("profiles/b.webp", b"profile-b")]
    service = OperationalBackupService(repository, encryption_secret="test-secret", staging_root=tmp_path / "staging")

    def dump(path: Path) -> None:
        path.write_bytes(b"postgres-custom-dump")

    result = service.create(
        create_database_dump=dump,
        source_objects=source,
        expected_objects=expected,
        table_counts={"books": 2, "users": 1},
        schema_revision="0021_email_outbox",
        deployment_revision="git-test",
        now=now,
    )
    return service, repository, result


def test_chunked_encryption_detects_corruption_and_leaves_no_plaintext(tmp_path: Path) -> None:
    source = tmp_path / "plain"
    encrypted = tmp_path / "encrypted"
    restored = tmp_path / "restored"
    source.write_bytes(b"sensitive" * 200_000)
    backup_id = uuid4()
    encrypt_file(source, encrypted, secret="secret", backup_id=backup_id)
    assert b"sensitive" not in encrypted.read_bytes()
    damaged = bytearray(encrypted.read_bytes())
    damaged[-20] ^= 1
    encrypted.write_bytes(damaged)
    with pytest.raises(BackupIntegrityError):
        decrypt_file(encrypted, restored, secret="secret", backup_id=backup_id)
    assert not restored.exists()


def test_complete_snapshot_verifies_and_restores_exact_objects(tmp_path: Path) -> None:
    service, repository, result = create_snapshot(tmp_path)
    assert f"snapshots/{result.backup_id}/complete.json" in repository.items
    assert all(b"covers/a.webp" not in value for value in repository.items.values())

    manifest = service.verify(result.backup_id)
    target = FilesystemCoverStorage(tmp_path / "target")
    service.restore_objects(result.backup_id, target)

    assert manifest["table_counts"] == {"books": 2, "users": 1}
    assert target.read("covers/a.webp") == b"cover-a"
    assert target.read("profiles/b.webp") == b"profile-b"


def test_restore_refuses_nonempty_target(tmp_path: Path) -> None:
    service, _, result = create_snapshot(tmp_path)
    target = FilesystemCoverStorage(tmp_path / "target")
    target.put("existing", b"do-not-touch")
    with pytest.raises(RuntimeError, match="not empty"):
        service.restore_objects(result.backup_id, target)
    assert target.read("existing") == b"do-not-touch"


def test_retention_removes_only_expired_complete_snapshot(tmp_path: Path) -> None:
    old_service, repository, old = create_snapshot(tmp_path / "old", now=datetime.now(UTC) - timedelta(days=31))
    new_source = FilesystemCoverStorage(tmp_path / "new-source")
    new_source.put("covers/a.webp", b"cover-a")
    new_source.put("profiles/b.webp", b"profile-b")
    expected = [object_entry("covers/a.webp", b"cover-a"), object_entry("profiles/b.webp", b"profile-b")]

    def dump(path: Path) -> None:
        path.write_bytes(b"new-dump")

    current = old_service.create(
        create_database_dump=dump,
        source_objects=new_source,
        expected_objects=expected,
        table_counts={},
        schema_revision="head",
        deployment_revision="new",
    )
    removed = old_service.prune(retention_days=30)
    assert removed == [old.backup_id]
    assert any(str(current.backup_id) in key for key in repository.items)
    assert not any(str(old.backup_id) in key for key in repository.items)


def test_full_restore_verifies_before_database_restore(tmp_path: Path) -> None:
    service, _, result = create_snapshot(tmp_path)
    target = FilesystemCoverStorage(tmp_path / "restore-target")
    calls: list[bytes] = []

    manifest = service.restore(
        result.backup_id,
        target_objects=target,
        ensure_database_empty=lambda: None,
        restore_database=lambda path: calls.append(path.read_bytes()),
        read_table_counts=lambda: {"books": 2, "users": 1},
    )

    assert calls == [b"postgres-custom-dump"]
    assert manifest["schema_revision"] == "0021_email_outbox"


def test_failed_database_restore_removes_objects_written_to_target(tmp_path: Path) -> None:
    service, _, result = create_snapshot(tmp_path)
    target = FilesystemCoverStorage(tmp_path / "restore-target")

    def fail(_: Path) -> None:
        raise RuntimeError("database rejected dump")

    with pytest.raises(RuntimeError, match="rejected"):
        service.restore(
            result.backup_id,
            target_objects=target,
            ensure_database_empty=lambda: None,
            restore_database=fail,
            read_table_counts=lambda: {},
        )
    assert list(target.iter_objects()) == []


def test_s3_repository_verifies_upload_download_and_small_markers(tmp_path: Path) -> None:
    client = FakeS3()
    repository = S3BackupRepository(client, bucket="backups", prefix="offsite")
    source = tmp_path / "source"
    target = tmp_path / "target"
    source.write_bytes(b"encrypted-artefact")
    digest = sha256(source.read_bytes()).hexdigest()
    repository.put_file("snapshots/id/data", source, sha256=digest)
    repository.get_file("snapshots/id/data", target, sha256=digest)
    repository.put_bytes("snapshots/id/complete.json", b"marker")
    assert target.read_bytes() == source.read_bytes()
    assert repository.get_bytes("snapshots/id/complete.json") == b"marker"

    content, metadata = client.items["offsite/snapshots/id/complete.json"]
    client.items["offsite/snapshots/id/complete.json"] = (content + b"x", metadata)
    with pytest.raises(OSError, match="verification"):
        repository.get_bytes("snapshots/id/complete.json")


def test_s3_repository_requires_and_applies_compliance_lock(tmp_path: Path) -> None:
    client = FakeS3()
    repository = S3BackupRepository(client, bucket="backups", prefix="offsite", object_lock_days=29)
    repository.check_ready()
    source = tmp_path / "source"
    source.write_bytes(b"encrypted")
    repository.put_file("snapshots/id/data", source, sha256=sha256(source.read_bytes()).hexdigest())
    assert client.last_upload_args["ObjectLockMode"] == "COMPLIANCE"
    assert client.last_upload_args["ObjectLockRetainUntilDate"] > datetime.now(UTC) + timedelta(days=28)


def test_postgres_tools_keep_password_out_of_process_arguments(monkeypatch, tmp_path: Path) -> None:
    captured: dict = {}

    def run(command, **kwargs) -> None:
        captured["command"] = command
        captured["environment"] = kwargs["env"]

    monkeypatch.setattr("bookpile_server.operational_backup.subprocess.run", run)
    tools = PostgresTools(
        "postgresql+psycopg://backup:private-password@db:5432/bookpile?sslmode=require"
    )
    tools.dump(tmp_path / "dump", snapshot="snapshot-id")

    assert "private-password" not in " ".join(captured["command"])
    assert captured["environment"]["PGPASSWORD"] == "private-password"
    assert captured["environment"]["PGSSLMODE"] == "require"


def test_backup_freshness_requires_recent_completion_marker(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    service, _, recent = create_snapshot(tmp_path / "recent", now=now - timedelta(hours=24))
    assert service.freshness(now=now).healthy is True
    assert service.freshness(now=now).latest_backup_id == recent.backup_id
    assert service.freshness(now=now + timedelta(hours=2)).healthy is False

    empty = OperationalBackupService(
        MemoryRepository(), encryption_secret="test-secret", staging_root=tmp_path / "empty"
    )
    assert empty.freshness(now=now).healthy is False
