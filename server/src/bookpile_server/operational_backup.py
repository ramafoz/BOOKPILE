"""Creation, verification, retention and guarded restore of service snapshots."""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.engine import make_url

from .backup_crypto import decrypt_file, encrypt_file
from .backup_repository import BackupRepository
from .cover_storage import CoverStorage
from .private_object_operations import ExpectedPrivateObject, audit_private_objects


FORMAT_VERSION = 1


@dataclass(frozen=True)
class SnapshotResult:
    backup_id: UUID
    created_at: datetime
    object_count: int
    database_bytes: int


@dataclass(frozen=True)
class BackupFreshness:
    healthy: bool
    latest_backup_id: UUID | None
    age_seconds: int | None


def file_digest(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


class PostgresTools:
    def __init__(self, database_url: str) -> None:
        url = make_url(database_url)
        self._database = url.database or ""
        self._environment = {
            "PGHOST": url.host or "",
            "PGPORT": str(url.port or 5432),
            "PGUSER": url.username or "",
            "PGPASSWORD": url.password or "",
            "PGDATABASE": self._database,
        }
        for query_name, environment_name in {
            "sslmode": "PGSSLMODE",
            "sslrootcert": "PGSSLROOTCERT",
            "sslcert": "PGSSLCERT",
            "sslkey": "PGSSLKEY",
        }.items():
            value = url.query.get(query_name)
            if value:
                self._environment[environment_name] = value

    def _run(self, command: list[str]) -> None:
        import os
        environment = os.environ.copy()
        environment.update(self._environment)
        subprocess.run(command, env=environment, check=True, capture_output=True)

    def dump(self, target: Path, *, snapshot: str) -> None:
        self._run(
            [
                "pg_dump",
                "--format=custom",
                "--compress=6",
                "--no-owner",
                "--no-privileges",
                f"--snapshot={snapshot}",
                f"--file={target}",
            ]
        )

    def restore(self, source: Path) -> None:
        self._run(
            [
                "pg_restore",
                "--exit-on-error",
                "--single-transaction",
                "--no-owner",
                "--no-privileges",
                f"--dbname={self._database}",
                str(source),
            ]
        )


class OperationalBackupService:
    def __init__(
        self,
        repository: BackupRepository,
        *,
        encryption_secret: str,
        encryption_key_id: str = "test",
        staging_root: Path,
        progress: Callable[[str, dict], None] | None = None,
    ) -> None:
        self.repository = repository
        self.secret = encryption_secret
        self.key_id = encryption_key_id
        self.staging_root = staging_root
        self.progress = progress or (lambda _event, _details: None)

    def _progress(self, event: str, **details) -> None:
        self.progress(event, details)

    def create(
        self,
        *,
        create_database_dump: Callable[[Path], None],
        source_objects: CoverStorage,
        expected_objects: list[ExpectedPrivateObject],
        table_counts: dict[str, int],
        schema_revision: str,
        deployment_revision: str,
        now: datetime | None = None,
    ) -> SnapshotResult:
        created_at = now or datetime.now(UTC)
        backup_id = uuid4()
        prefix = f"snapshots/{backup_id}"
        uploaded: list[str] = []
        self.staging_root.mkdir(parents=True, exist_ok=True)
        try:
            with TemporaryDirectory(dir=self.staging_root) as directory:
                work = Path(directory)
                database = work / "database.dump"
                create_database_dump(database)
                if not database.is_file() or not database.stat().st_size:
                    raise RuntimeError("PostgreSQL produced an empty dump")
                database_plain = {"byte_size": database.stat().st_size, "sha256": file_digest(database)}
                self._progress("database_dumped", byte_size=database_plain["byte_size"])
                encrypted_database = work / "database.bpbk"
                database_cipher_size, database_cipher_hash = encrypt_file(
                    database,
                    encrypted_database,
                    secret=self.secret,
                    backup_id=backup_id,
                )
                database_key = f"{prefix}/database.bpbk"
                self.repository.put_file(database_key, encrypted_database, sha256=database_cipher_hash)
                uploaded.append(database_key)
                self._progress("database_uploaded", byte_size=database_cipher_size)

                object_manifest: list[dict] = []
                for index, expected in enumerate(expected_objects):
                    content = source_objects.read(expected.object_key)
                    if len(content) != expected.byte_size or sha256(content).hexdigest() != expected.sha256:
                        raise RuntimeError("A private object changed or disappeared during backup")
                    plain = work / "object.bin"
                    plain.write_bytes(content)
                    encrypted = work / "object.bpbk"
                    cipher_size, cipher_hash = encrypt_file(plain, encrypted, secret=self.secret, backup_id=backup_id)
                    key = f"{prefix}/objects/{index:08d}.bpbk"
                    self.repository.put_file(key, encrypted, sha256=cipher_hash)
                    uploaded.append(key)
                    object_manifest.append({
                        "object_key": expected.object_key,
                        "byte_size": expected.byte_size,
                        "sha256": expected.sha256,
                        "artefact": {"key": key, "byte_size": cipher_size, "sha256": cipher_hash},
                    })
                    if (index + 1) % 25 == 0 or index + 1 == len(expected_objects):
                        self._progress("objects_uploaded", processed=index + 1, total=len(expected_objects))

                manifest = {
                    "format_version": FORMAT_VERSION,
                    "backup_id": str(backup_id),
                    "created_at": created_at.isoformat(),
                    "schema_revision": schema_revision,
                    "deployment_revision": deployment_revision,
                    "encryption_key_id": self.key_id,
                    "table_counts": dict(sorted(table_counts.items())),
                    "database": {
                        "plain": database_plain,
                        "artefact": {
                            "key": database_key,
                            "byte_size": database_cipher_size,
                            "sha256": database_cipher_hash,
                        },
                    },
                    "objects": object_manifest,
                }
                manifest_plain = work / "manifest.json"
                manifest_plain.write_text(json.dumps(manifest, sort_keys=True, separators=(",", ":")), encoding="utf-8")
                manifest_encrypted = work / "manifest.bpbk"
                manifest_size, manifest_hash = encrypt_file(
                    manifest_plain,
                    manifest_encrypted,
                    secret=self.secret,
                    backup_id=backup_id,
                )
                manifest_key = f"{prefix}/manifest.bpbk"
                self.repository.put_file(manifest_key, manifest_encrypted, sha256=manifest_hash)
                uploaded.append(manifest_key)
                marker = json.dumps({
                    "format_version": FORMAT_VERSION,
                    "backup_id": str(backup_id),
                    "created_at": created_at.isoformat(),
                    "encryption_key_id": self.key_id,
                    "manifest": {"key": manifest_key, "byte_size": manifest_size, "sha256": manifest_hash},
                }, sort_keys=True, separators=(",", ":")).encode("utf-8")
                self.repository.put_bytes(f"{prefix}/complete.json", marker)
                self._progress("snapshot_completed", object_count=len(expected_objects))
            return SnapshotResult(backup_id, created_at, len(expected_objects), database_plain["byte_size"])
        except Exception:
            try:
                self.repository.delete_keys(uploaded)
            except Exception:
                # Compliance-locked incomplete artefacts are harmless without
                # a completion marker and expire through bucket lifecycle.
                pass
            raise

    def _load_manifest(self, backup_id: UUID, work: Path) -> dict:
        marker_key = f"snapshots/{backup_id}/complete.json"
        marker = json.loads(self.repository.get_bytes(marker_key))
        if marker.get("format_version") != FORMAT_VERSION or marker.get("backup_id") != str(backup_id):
            raise RuntimeError("Invalid backup completion marker")
        if marker.get("encryption_key_id") != self.key_id:
            raise RuntimeError("Snapshot requires another backup encryption key")
        encrypted = work / "manifest.bpbk"
        manifest_info = marker["manifest"]
        self.repository.get_file(manifest_info["key"], encrypted, sha256=manifest_info["sha256"])
        plain = work / "manifest.json"
        decrypt_file(encrypted, plain, secret=self.secret, backup_id=backup_id)
        manifest = json.loads(plain.read_text(encoding="utf-8"))
        if manifest.get("format_version") != FORMAT_VERSION or manifest.get("backup_id") != str(backup_id):
            raise RuntimeError("Backup manifest identity mismatch")
        if manifest.get("encryption_key_id") != self.key_id:
            raise RuntimeError("Backup manifest encryption key mismatch")
        return manifest

    def verify(self, backup_id: UUID) -> dict:
        self.staging_root.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(dir=self.staging_root) as directory:
            work = Path(directory)
            manifest = self._load_manifest(backup_id, work)
            artefacts = [manifest["database"]] + manifest["objects"]
            for index, item in enumerate(artefacts):
                encrypted = work / f"verify-{index}.bpbk"
                plain = work / f"verify-{index}.bin"
                info = item["artefact"]
                self.repository.get_file(info["key"], encrypted, sha256=info["sha256"])
                size, digest = decrypt_file(encrypted, plain, secret=self.secret, backup_id=backup_id)
                expected = item.get("plain", item)
                if size != expected["byte_size"] or digest != expected["sha256"]:
                    raise RuntimeError("Backup plaintext verification failed")
                encrypted.unlink()
                plain.unlink()
                if (index + 1) % 25 == 0 or index + 1 == len(artefacts):
                    self._progress("artefacts_verified", processed=index + 1, total=len(artefacts))
            return manifest

    def prune(self, *, retention_days: int, now: datetime | None = None) -> list[UUID]:
        cutoff = (now or datetime.now(UTC)) - timedelta(days=retention_days)
        removed: list[UUID] = []
        for key in self.repository.list_keys("snapshots"):
            if not key.endswith("/complete.json"):
                continue
            marker = json.loads(self.repository.get_bytes(key))
            created = datetime.fromisoformat(marker["created_at"])
            if created < cutoff:
                backup_id = UUID(marker["backup_id"])
                self.repository.delete_keys(self.repository.list_keys(f"snapshots/{backup_id}"))
                removed.append(backup_id)
        return removed

    def freshness(
        self, *, max_age_hours: int = 25, now: datetime | None = None
    ) -> BackupFreshness:
        moment = now or datetime.now(UTC)
        latest: tuple[datetime, UUID] | None = None
        for key in self.repository.list_keys("snapshots"):
            if not key.endswith("/complete.json"):
                continue
            marker = json.loads(self.repository.get_bytes(key))
            created = datetime.fromisoformat(marker["created_at"])
            backup_id = UUID(marker["backup_id"])
            if latest is None or created > latest[0]:
                latest = (created, backup_id)
        if latest is None:
            return BackupFreshness(False, None, None)
        age = int((moment - latest[0]).total_seconds())
        healthy = -300 <= age <= max_age_hours * 3600
        return BackupFreshness(healthy, latest[1], age)

    def restore_objects(self, backup_id: UUID, target: CoverStorage) -> dict:
        if next(iter(target.iter_objects()), None) is not None:
            raise RuntimeError("Restore target object storage is not empty")
        restored: list[str] = []
        self.staging_root.mkdir(parents=True, exist_ok=True)
        try:
            with TemporaryDirectory(dir=self.staging_root) as directory:
                work = Path(directory)
                manifest = self._load_manifest(backup_id, work)
                for index, item in enumerate(manifest["objects"]):
                    encrypted = work / f"restore-{index}.bpbk"
                    plain = work / f"restore-{index}.bin"
                    info = item["artefact"]
                    self.repository.get_file(info["key"], encrypted, sha256=info["sha256"])
                    size, digest = decrypt_file(encrypted, plain, secret=self.secret, backup_id=backup_id)
                    if size != item["byte_size"] or digest != item["sha256"]:
                        raise RuntimeError("Backup object verification failed")
                    target.put(item["object_key"], plain.read_bytes())
                    restored.append(item["object_key"])
                expected = [
                    ExpectedPrivateObject(
                        item["object_key"], item["byte_size"], item["sha256"]
                    )
                    for item in manifest["objects"]
                ]
                if not audit_private_objects(expected, target.iter_objects()).is_exact:
                    raise RuntimeError("Restored object inventory does not match the snapshot")
                return manifest
        except Exception:
            for key in restored:
                target.delete(key)
            raise

    def restore(
        self,
        backup_id: UUID,
        *,
        target_objects: CoverStorage,
        ensure_database_empty: Callable[[], None],
        restore_database: Callable[[Path], None],
        read_table_counts: Callable[[], dict[str, int]],
    ) -> dict:
        """Verify everything before mutating, then restore objects and DB safely."""

        if next(iter(target_objects.iter_objects()), None) is not None:
            raise RuntimeError("Restore target object storage is not empty")
        ensure_database_empty()
        self.staging_root.mkdir(parents=True, exist_ok=True)
        restored_keys: list[str] = []
        try:
            with TemporaryDirectory(dir=self.staging_root) as directory:
                work = Path(directory)
                manifest = self._load_manifest(backup_id, work)
                database_info = manifest["database"]
                database_encrypted = work / "database.bpbk"
                database_plain = work / "database.dump"
                artefact = database_info["artefact"]
                self.repository.get_file(artefact["key"], database_encrypted, sha256=artefact["sha256"])
                size, digest = decrypt_file(database_encrypted, database_plain, secret=self.secret, backup_id=backup_id)
                if size != database_info["plain"]["byte_size"] or digest != database_info["plain"]["sha256"]:
                    raise RuntimeError("Backup database verification failed")

                # First pass authenticates every artefact without mutating the
                # target or retaining the full object set on local disk.
                for index, item in enumerate(manifest["objects"]):
                    encrypted = work / f"object-{index}.bpbk"
                    plain = work / f"object-{index}.bin"
                    info = item["artefact"]
                    self.repository.get_file(info["key"], encrypted, sha256=info["sha256"])
                    object_size, object_hash = decrypt_file(encrypted, plain, secret=self.secret, backup_id=backup_id)
                    if object_size != item["byte_size"] or object_hash != item["sha256"]:
                        raise RuntimeError("Backup object verification failed")
                    encrypted.unlink()
                    plain.unlink()
                    if (index + 1) % 25 == 0 or index + 1 == len(manifest["objects"]):
                        self._progress("restore_artefacts_staged", processed=index + 1, total=len(manifest["objects"]))

                # Recheck immediately before the first external mutation.
                ensure_database_empty()
                if next(iter(target_objects.iter_objects()), None) is not None:
                    raise RuntimeError("Restore target object storage ceased to be empty")
                # Second pass writes one already-proven artefact at a time.
                for index, item in enumerate(manifest["objects"]):
                    encrypted = work / "restore-object.bpbk"
                    plain = work / "restore-object.bin"
                    info = item["artefact"]
                    self.repository.get_file(info["key"], encrypted, sha256=info["sha256"])
                    size, digest = decrypt_file(encrypted, plain, secret=self.secret, backup_id=backup_id)
                    if size != item["byte_size"] or digest != item["sha256"]:
                        raise RuntimeError("Backup object changed between verification and restore")
                    target_objects.put(item["object_key"], plain.read_bytes())
                    restored_keys.append(item["object_key"])
                    encrypted.unlink()
                    plain.unlink()
                    if len(restored_keys) % 25 == 0 or len(restored_keys) == len(manifest["objects"]):
                        self._progress(
                            "restore_objects_written",
                            processed=len(restored_keys),
                            total=len(manifest["objects"]),
                        )
                restore_database(database_plain)
                self._progress("restore_database_written", table_count=len(manifest["table_counts"]))
                actual_counts = read_table_counts()
                if actual_counts != manifest["table_counts"]:
                    raise RuntimeError("Restored PostgreSQL table counts do not match the snapshot")
                expected = [
                    ExpectedPrivateObject(
                        item["object_key"], item["byte_size"], item["sha256"]
                    )
                    for item in manifest["objects"]
                ]
                if not audit_private_objects(expected, target_objects.iter_objects()).is_exact:
                    raise RuntimeError("Restored private-object inventory does not match the snapshot")
                self._progress("restore_verified", object_count=len(expected), table_count=len(actual_counts))
                return manifest
        except Exception:
            for key in restored_keys:
                target_objects.delete(key)
            raise
