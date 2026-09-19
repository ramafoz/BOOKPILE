from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path, PurePosixPath
from typing import TYPE_CHECKING, Any, Iterator, Protocol

import boto3
from botocore.config import Config

if TYPE_CHECKING:
    from .config import Settings


@dataclass(frozen=True)
class StoredObjectInfo:
    object_key: str
    byte_size: int
    sha256: str | None


class CoverStorage(Protocol):
    def put(self, object_key: str, content: bytes) -> None: ...
    def read(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str) -> None: ...
    def check_ready(self) -> None: ...
    def stat(self, object_key: str) -> StoredObjectInfo | None: ...
    def iter_objects(self) -> Iterator[StoredObjectInfo]: ...


def _validate_object_key(object_key: str) -> str:
    path = PurePosixPath(object_key)
    if (
        not object_key
        or object_key.startswith("/")
        or "\\" in object_key
        or any(part in {"", ".", ".."} for part in path.parts)
    ):
        raise ValueError("Invalid private object key")
    return path.as_posix()


class FilesystemCoverStorage:
    """Private development storage; object keys never become public paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, object_key: str) -> Path:
        path = (self._root / _validate_object_key(object_key)).resolve()
        if self._root not in path.parents:
            raise ValueError("Private object key escapes its storage root")
        return path

    def put(self, object_key: str, content: bytes) -> None:
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(content)
        temporary.replace(path)

    def read(self, object_key: str) -> bytes:
        return self._path(object_key).read_bytes()

    def delete(self, object_key: str) -> None:
        self._path(object_key).unlink(missing_ok=True)

    def check_ready(self) -> None:
        self._root.mkdir(parents=True, exist_ok=True)
        if not self._root.is_dir():
            raise OSError("Private object storage root is not a directory")

    def stat(self, object_key: str) -> StoredObjectInfo | None:
        path = self._path(object_key)
        if not path.is_file():
            return None
        content = path.read_bytes()
        return StoredObjectInfo(object_key, len(content), sha256(content).hexdigest())

    def iter_objects(self) -> Iterator[StoredObjectInfo]:
        if not self._root.exists():
            return
        for path in sorted(item for item in self._root.rglob("*") if item.is_file()):
            if path.name.endswith(".partial"):
                continue
            object_key = path.relative_to(self._root).as_posix()
            content = path.read_bytes()
            yield StoredObjectInfo(object_key, len(content), sha256(content).hexdigest())


class S3PrivateObjectStorage:
    """Private S3-compatible storage with verified writes and bounded I/O."""

    checksum_metadata_key = "bookpile-sha256"

    def __init__(self, client: Any, *, bucket: str, prefix: str) -> None:
        self._client = client
        self._bucket = bucket
        self._prefix = prefix.strip("/")

    @classmethod
    def from_settings(cls, settings: "Settings") -> "S3PrivateObjectStorage":
        secret = settings.private_object_s3_secret_access_key
        client = boto3.client(
            "s3",
            endpoint_url=settings.private_object_s3_endpoint_url,
            region_name=settings.private_object_s3_region,
            aws_access_key_id=settings.private_object_s3_access_key_id,
            aws_secret_access_key=(secret.get_secret_value() if secret else None),
            use_ssl=True,
            config=Config(
                signature_version="s3v4",
                connect_timeout=settings.private_object_s3_connect_timeout_seconds,
                read_timeout=settings.private_object_s3_read_timeout_seconds,
                max_pool_connections=settings.private_object_s3_max_connections,
                retries={
                    "max_attempts": settings.private_object_s3_max_attempts,
                    "mode": "standard",
                },
                s3={"addressing_style": settings.private_object_s3_addressing_style},
            ),
        )
        return cls(
            client,
            bucket=settings.private_object_s3_bucket or "",
            prefix=settings.private_object_s3_prefix,
        )

    def _remote_key(self, object_key: str) -> str:
        return f"{self._prefix}/{_validate_object_key(object_key)}"

    def _logical_key(self, remote_key: str) -> str | None:
        prefix = f"{self._prefix}/"
        if not remote_key.startswith(prefix):
            return None
        return _validate_object_key(remote_key.removeprefix(prefix))

    def put(self, object_key: str, content: bytes) -> None:
        remote_key = self._remote_key(object_key)
        digest = sha256(content).hexdigest()
        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=remote_key,
                Body=content,
                ContentLength=len(content),
                ContentType="application/octet-stream",
                Metadata={self.checksum_metadata_key: digest},
            )
        except Exception as exc:
            raise OSError("S3 object write failed") from exc
        try:
            stored = self.stat(object_key)
            valid = (
                stored is not None
                and stored.byte_size == len(content)
                and stored.sha256 == digest
                and sha256(self.read(object_key)).hexdigest() == digest
            )
        except Exception as exc:
            valid = False
            verification_error = exc
        else:
            verification_error = None
        if not valid:
            try:
                self._client.delete_object(Bucket=self._bucket, Key=remote_key)
            except Exception:
                pass
            raise OSError("S3 write verification failed") from verification_error

    def read(self, object_key: str) -> bytes:
        try:
            response = self._client.get_object(
                Bucket=self._bucket,
                Key=self._remote_key(object_key),
            )
            body = response["Body"]
            parts: list[bytes] = []
            digest = sha256()
            total = 0
            try:
                while chunk := body.read(1024 * 1024):
                    parts.append(chunk)
                    digest.update(chunk)
                    total += len(chunk)
            finally:
                body.close()
            expected_size = int(response.get("ContentLength", total))
            expected_hash = response.get("Metadata", {}).get(self.checksum_metadata_key)
            if (
                total != expected_size
                or not expected_hash
                or digest.hexdigest() != expected_hash
            ):
                raise OSError("S3 object integrity verification failed")
            return b"".join(parts)
        except (OSError, ValueError):
            raise
        except Exception as exc:
            raise OSError("S3 object read failed") from exc

    def delete(self, object_key: str) -> None:
        remote_key = self._remote_key(object_key)
        try:
            self._client.delete_object(
                Bucket=self._bucket,
                Key=remote_key,
            )
        except Exception as exc:
            raise OSError("S3 object deletion failed") from exc

    def check_ready(self) -> None:
        try:
            self._client.head_bucket(Bucket=self._bucket)
        except Exception as exc:
            raise OSError("S3 bucket is unavailable") from exc

    def stat(self, object_key: str) -> StoredObjectInfo | None:
        remote_key = self._remote_key(object_key)
        try:
            response = self._client.head_object(
                Bucket=self._bucket,
                Key=remote_key,
            )
        except Exception as exc:
            response_code = getattr(exc, "response", {}).get("Error", {}).get("Code")
            if response_code in {"404", "NoSuchKey", "NotFound"}:
                return None
            raise OSError("S3 object metadata read failed") from exc
        return StoredObjectInfo(
            object_key=_validate_object_key(object_key),
            byte_size=int(response["ContentLength"]),
            sha256=response.get("Metadata", {}).get(self.checksum_metadata_key),
        )

    def iter_objects(self) -> Iterator[StoredObjectInfo]:
        try:
            paginator = self._client.get_paginator("list_objects_v2")
            for page in paginator.paginate(
                Bucket=self._bucket,
                Prefix=f"{self._prefix}/",
            ):
                for item in page.get("Contents", []):
                    logical_key = self._logical_key(item["Key"])
                    if logical_key is None:
                        continue
                    stored = self.stat(logical_key)
                    if stored is not None:
                        content = self.read(logical_key)
                        yield StoredObjectInfo(
                            logical_key,
                            len(content),
                            sha256(content).hexdigest(),
                        )
        except OSError:
            raise
        except Exception as exc:
            raise OSError("S3 object inventory failed") from exc
