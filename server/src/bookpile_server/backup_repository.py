"""Off-site repository boundary for encrypted operational snapshots."""

from pathlib import Path, PurePosixPath
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from .config import Settings


def validate_backup_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or key.startswith("/") or "\\" in key or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("Invalid backup repository key")
    return path.as_posix()


class BackupRepository(Protocol):
    def put_file(self, key: str, source: Path, *, sha256: str) -> None: ...
    def get_file(self, key: str, target: Path, *, sha256: str) -> None: ...
    def put_bytes(self, key: str, content: bytes) -> None: ...
    def get_bytes(self, key: str) -> bytes: ...
    def list_keys(self, prefix: str) -> list[str]: ...
    def delete_keys(self, keys: list[str]) -> None: ...


class S3BackupRepository:
    checksum_metadata_key = "bookpile-sha256"

    def __init__(self, client: Any, *, bucket: str, prefix: str, object_lock_days: int = 0) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")
        self._object_lock_days = object_lock_days

    @classmethod
    def from_settings(cls, settings: "Settings") -> "S3BackupRepository":
        secret = settings.operational_backup_s3_secret_access_key
        client = boto3.client(
            "s3",
            endpoint_url=settings.operational_backup_s3_endpoint_url,
            region_name=settings.operational_backup_s3_region,
            aws_access_key_id=settings.operational_backup_s3_access_key_id,
            aws_secret_access_key=secret.get_secret_value() if secret else None,
            use_ssl=True,
            config=Config(
                signature_version="s3v4",
                connect_timeout=settings.private_object_s3_connect_timeout_seconds,
                read_timeout=settings.private_object_s3_read_timeout_seconds,
                max_pool_connections=settings.private_object_s3_max_connections,
                retries={"max_attempts": settings.private_object_s3_max_attempts, "mode": "standard"},
                s3={"addressing_style": settings.private_object_s3_addressing_style},
            ),
        )
        return cls(
            client,
            bucket=settings.operational_backup_s3_bucket or "",
            prefix=settings.operational_backup_s3_prefix,
            object_lock_days=(
                settings.operational_backup_retention_days
                if settings.operational_backup_object_lock_enabled
                else 0
            ),
        )

    def check_ready(self) -> None:
        self._client.head_bucket(Bucket=self._bucket)
        if self._object_lock_days:
            versioning = self._client.get_bucket_versioning(Bucket=self._bucket)
            lock = self._client.get_object_lock_configuration(Bucket=self._bucket)
            object_lock_enabled = lock.get("ObjectLockConfiguration", {}).get(
                "ObjectLockEnabled"
            )
            if versioning.get("Status") != "Enabled" or object_lock_enabled != "Enabled":
                raise OSError("Backup bucket requires versioning and Object Lock")

    def _lock_args(self) -> dict:
        if not self._object_lock_days:
            return {}
        return {
            "ObjectLockMode": "COMPLIANCE",
            "ObjectLockRetainUntilDate": datetime.now(UTC) + timedelta(days=self._object_lock_days),
        }

    def _remote(self, key: str) -> str:
        return f"{self._prefix}/{validate_backup_key(key)}"

    def _logical(self, key: str) -> str | None:
        prefix = f"{self._prefix}/"
        return validate_backup_key(key.removeprefix(prefix)) if key.startswith(prefix) else None

    def put_file(self, key: str, source: Path, *, sha256: str) -> None:
        with source.open("rb") as stream:
            self._client.upload_fileobj(
                stream,
                self._bucket,
                self._remote(key),
                ExtraArgs={
                    "ContentType": "application/octet-stream",
                    "Metadata": {self.checksum_metadata_key: sha256},
                    **self._lock_args(),
                },
            )
        head = self._client.head_object(Bucket=self._bucket, Key=self._remote(key))
        stored_hash = head.get("Metadata", {}).get(self.checksum_metadata_key)
        if int(head["ContentLength"]) != source.stat().st_size or stored_hash != sha256:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=self._remote(key))
            except Exception:
                pass
            raise OSError("Off-site backup write verification failed")

    def get_file(self, key: str, target: Path, *, sha256: str) -> None:
        from hashlib import sha256 as new_hash

        temporary = target.with_suffix(target.suffix + ".partial")
        temporary.parent.mkdir(parents=True, exist_ok=True)
        try:
            with temporary.open("wb") as stream:
                self._client.download_fileobj(self._bucket, self._remote(key), stream)
            digest = new_hash()
            with temporary.open("rb") as stream:
                while chunk := stream.read(1024 * 1024):
                    digest.update(chunk)
            if digest.hexdigest() != sha256:
                raise OSError("Off-site backup download verification failed")
            temporary.replace(target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def put_bytes(self, key: str, content: bytes) -> None:
        from hashlib import sha256
        digest = sha256(content).hexdigest()
        self._client.put_object(
            Bucket=self._bucket,
            Key=self._remote(key),
            Body=content,
            Metadata={self.checksum_metadata_key: digest},
            **self._lock_args(),
        )
        if self.get_bytes(key) != content:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=self._remote(key))
            except Exception:
                pass
            raise OSError("Off-site backup marker verification failed")

    def get_bytes(self, key: str) -> bytes:
        from hashlib import sha256
        response = self._client.get_object(Bucket=self._bucket, Key=self._remote(key))
        body = response["Body"]
        try:
            content = body.read()
        finally:
            body.close()
        expected = response.get("Metadata", {}).get(self.checksum_metadata_key)
        if not expected or sha256(content).hexdigest() != expected:
            raise OSError("Off-site backup object verification failed")
        return content

    def list_keys(self, prefix: str) -> list[str]:
        keys: list[str] = []
        paginator = self._client.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=self._bucket, Prefix=self._remote(prefix)):
            for item in page.get("Contents", []):
                logical = self._logical(item["Key"])
                if logical is not None:
                    keys.append(logical)
        return sorted(keys)

    def delete_keys(self, keys: list[str]) -> None:
        for offset in range(0, len(keys), 1000):
            batch = keys[offset:offset + 1000]
            if batch:
                self._client.delete_objects(
                    Bucket=self._bucket,
                    Delete={
                        "Objects": [{"Key": self._remote(key)} for key in batch],
                        "Quiet": True,
                    },
                )
