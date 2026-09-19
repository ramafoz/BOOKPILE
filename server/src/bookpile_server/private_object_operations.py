from dataclasses import dataclass
from hashlib import sha256
from secrets import token_bytes
from typing import Iterable
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session

from .cover_storage import CoverStorage, StoredObjectInfo
from .models import BookCover, UserProfileImage


@dataclass(frozen=True)
class ExpectedPrivateObject:
    object_key: str
    byte_size: int
    sha256: str


@dataclass(frozen=True)
class PrivateObjectAudit:
    expected_count: int
    stored_count: int
    missing: tuple[str, ...]
    orphaned: tuple[str, ...]
    mismatched: tuple[str, ...]

    @property
    def is_exact(self) -> bool:
        return not (self.missing or self.orphaned or self.mismatched)


@dataclass(frozen=True)
class PrivateObjectMigration:
    expected_count: int
    already_verified: int
    copied: int
    planned: int
    final_audit: PrivateObjectAudit | None


def probe_private_object_storage(storage: CoverStorage, *, byte_size: int = 1024) -> int:
    """Verify an isolated write/read/delete cycle without touching library objects."""
    if byte_size < 1:
        raise ValueError("Probe byte size must be positive")
    storage.check_ready()
    object_key = f"_provider-probe/{uuid4().hex}.bin"
    if storage.stat(object_key) is not None:
        raise RuntimeError("Private-object probe key unexpectedly exists")
    content = token_bytes(byte_size)
    try:
        storage.put(object_key, content)
        info = storage.stat(object_key)
        if (
            info is None
            or info.byte_size != byte_size
            or info.sha256 != sha256(content).hexdigest()
            or storage.read(object_key) != content
        ):
            raise RuntimeError("Private-object provider probe verification failed")
    finally:
        storage.delete(object_key)
    if storage.stat(object_key) is not None:
        raise RuntimeError("Private-object provider probe cleanup failed")
    return byte_size


def expected_private_objects(session: Session) -> list[ExpectedPrivateObject]:
    covers = session.execute(
        select(BookCover.object_key, BookCover.byte_size, BookCover.sha256)
        .order_by(BookCover.object_key)
    ).all()
    profiles = session.execute(
        select(
            UserProfileImage.object_key,
            UserProfileImage.byte_size,
            UserProfileImage.sha256,
        ).order_by(UserProfileImage.object_key)
    ).all()
    expected = [
        ExpectedPrivateObject(key, int(size), digest)
        for key, size, digest in (*covers, *profiles)
    ]
    if len({item.object_key for item in expected}) != len(expected):
        raise RuntimeError("Database private-object keys are not unique")
    return sorted(expected, key=lambda item: item.object_key)


def audit_private_objects(
    expected: Iterable[ExpectedPrivateObject],
    stored: Iterable[StoredObjectInfo],
) -> PrivateObjectAudit:
    expected_by_key = {item.object_key: item for item in expected}
    stored_by_key = {item.object_key: item for item in stored}
    shared = expected_by_key.keys() & stored_by_key.keys()
    mismatched = tuple(
        sorted(
            key
            for key in shared
            if stored_by_key[key].byte_size != expected_by_key[key].byte_size
            or stored_by_key[key].sha256 != expected_by_key[key].sha256
        )
    )
    return PrivateObjectAudit(
        expected_count=len(expected_by_key),
        stored_count=len(stored_by_key),
        missing=tuple(sorted(expected_by_key.keys() - stored_by_key.keys())),
        orphaned=tuple(sorted(stored_by_key.keys() - expected_by_key.keys())),
        mismatched=mismatched,
    )


def migrate_private_objects(
    expected: Iterable[ExpectedPrivateObject],
    source: CoverStorage,
    target: CoverStorage,
    *,
    apply: bool,
) -> PrivateObjectMigration:
    expected_items = list(expected)
    source_audit = audit_private_objects(expected_items, source.iter_objects())
    if source_audit.missing or source_audit.mismatched:
        raise RuntimeError("Source storage does not match database metadata")

    already_verified = 0
    copied = 0
    planned = 0
    for item in expected_items:
        target_info = target.stat(item.object_key)
        if (
            target_info is not None
            and target_info.byte_size == item.byte_size
            and target_info.sha256 == item.sha256
        ):
            try:
                target_content = target.read(item.object_key)
            except OSError:
                pass
            else:
                if (
                    len(target_content) == item.byte_size
                    and sha256(target_content).hexdigest() == item.sha256
                ):
                    already_verified += 1
                    continue
        if not apply:
            planned += 1
            continue
        content = source.read(item.object_key)
        if len(content) != item.byte_size or sha256(content).hexdigest() != item.sha256:
            raise RuntimeError("Source object changed during migration")
        target.put(item.object_key, content)
        copied += 1

    final_audit = (
        audit_private_objects(expected_items, target.iter_objects()) if apply else None
    )
    if final_audit is not None and not final_audit.is_exact:
        raise RuntimeError("Target storage verification failed")
    return PrivateObjectMigration(
        expected_count=len(expected_items),
        already_verified=already_verified,
        copied=copied,
        planned=planned,
        final_audit=final_audit,
    )
