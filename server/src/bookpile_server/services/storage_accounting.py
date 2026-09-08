"""Versioned logical accounting over persisted Server records."""
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Base,
    BookCover,
    UserProfileImage,
)
from .storage_domain import logical_collection_bytes


_STORAGE_TABLES = {
    "account_storage_entitlements",
    "library_storage_usages",
    "library_storage_allocations",
    "library_deletion_tombstones",
}


def _payload(row) -> dict[str, object]:
    return {column: value for column, value in row._mapping.items()}


def calculate_library_logical_bytes(session: Session, library_id: UUID) -> int:
    records: list[tuple[str, object]] = []
    libraries = Base.metadata.tables["libraries"]
    library_row = session.execute(
        select(libraries).where(libraries.c.id == library_id)
    ).first()
    if library_row is None:
        raise LookupError("Library does not exist.")
    records.append(("libraries", _payload(library_row)))

    for name, table in sorted(Base.metadata.tables.items()):
        if name == "libraries" or name in _STORAGE_TABLES or "library_id" not in table.c:
            continue
        rows = session.execute(
            select(table).where(table.c.library_id == library_id)
        ).all()
        records.extend((name, _payload(row)) for row in rows)

    object_bytes = session.scalars(
        select(BookCover.byte_size).where(BookCover.library_id == library_id)
    ).all()
    return logical_collection_bytes(records, object_bytes=object_bytes)


def calculate_account_data_bytes(session: Session, user_id: UUID) -> int:
    records: list[tuple[str, object]] = []
    for name in ("user_profiles", "user_profile_field_visibilities", "user_profile_images"):
        table = Base.metadata.tables[name]
        rows = session.execute(select(table).where(table.c.user_id == user_id)).all()
        records.extend((name, _payload(row)) for row in rows)
    image_bytes = session.scalar(
        select(UserProfileImage.byte_size).where(UserProfileImage.user_id == user_id)
    )
    return logical_collection_bytes(records, object_bytes=[image_bytes] if image_bytes else [])
