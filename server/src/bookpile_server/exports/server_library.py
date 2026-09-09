from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
from typing import Any
from uuid import UUID
import zipfile

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..cover_storage import CoverStorage
from ..models import (
    Book,
    BookContributor,
    BookCover,
    Bookcase,
    Container,
    Library,
    LibraryMembership,
    Loan,
    PersonalBookRecord,
    ReadingSession,
    Shelf,
    VisualBookcaseLayout,
    VisualContainerLayout,
    VisualOutsideArea,
    VisualShelfLayout,
)


SERVER_LIBRARY_EXPORT_FORMAT = "BOOKPILE_SERVER_LIBRARY"
SERVER_LIBRARY_EXPORT_VERSION = 1
SERVER_LIBRARY_DATA_SCHEMA = 1


class PortableExportError(ValueError):
    pass


def _json_value(value: Any) -> Any:
    if isinstance(value, (UUID, date, datetime, Decimal)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise PortableExportError(f"Unsupported portable value: {type(value).__name__}")


def _model_rows(session: Session, model, library_id: UUID) -> list[dict[str, Any]]:
    rows = session.scalars(
        select(model).where(model.library_id == library_id).order_by(*model.__table__.primary_key.columns)
    )
    return [
        {
            column.name: _json_value(getattr(row, column.name))
            for column in model.__table__.columns
        }
        for row in rows
    ]


def _encoded_json(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def create_server_library_export(
    *,
    session: Session,
    storage: CoverStorage,
    library_id: UUID,
    destination: Path,
) -> dict[str, Any]:
    library = session.get(Library, library_id)
    if library is None or library.state != "active":
        raise PortableExportError("Library not found.")
    memberships = list(
        session.scalars(
            select(LibraryMembership)
            .where(LibraryMembership.library_id == library_id)
            .order_by(LibraryMembership.user_id)
        )
    )
    members = [
        {
            "member_key": str(item.user_id),
            "username": item.user.username,
            "role": item.role,
            "viewer_scope": item.viewer_scope,
            "selected_reading_member_key": (
                str(item.selected_reading_user_id) if item.selected_reading_user_id else None
            ),
        }
        for item in memberships
    ]
    model_groups = {
        "bookcases": Bookcase,
        "shelves": Shelf,
        "containers": Container,
        "books": Book,
        "contributors": BookContributor,
        "readings": ReadingSession,
        "loans": Loan,
        "personal_book_records": PersonalBookRecord,
        "bookcase_layouts": VisualBookcaseLayout,
        "shelf_layouts": VisualShelfLayout,
        "container_layouts": VisualContainerLayout,
        "outside_areas": VisualOutsideArea,
    }
    data: dict[str, Any] = {
        "schema_version": SERVER_LIBRARY_DATA_SCHEMA,
        "library": {
            "source_library_id": str(library.id),
            "name": library.name,
            "geometry_mode": library.geometry_mode,
            "coordinate_system_version": library.coordinate_system_version,
            "created_at": _json_value(library.created_at),
            "updated_at": _json_value(library.updated_at),
        },
        "members": members,
    }
    for name, model in model_groups.items():
        data[name] = _model_rows(session, model, library_id)

    cover_rows = list(
        session.scalars(
            select(BookCover)
            .where(BookCover.library_id == library_id)
            .order_by(BookCover.book_id)
        )
    )
    cover_files: list[tuple[str, bytes]] = []
    data["covers"] = []
    for cover in cover_rows:
        content = storage.read(cover.object_key)
        if len(content) != cover.byte_size or sha256(content).hexdigest() != cover.sha256:
            raise PortableExportError("A private cover failed export verification.")
        archive_name = f"covers/{cover.book_id}.webp"
        cover_files.append((archive_name, content))
        data["covers"].append(
            {
                "source_id": str(cover.id),
                "book_id": str(cover.book_id),
                "archive_name": archive_name,
                "media_type": cover.media_type,
                "byte_size": cover.byte_size,
                "width_px": cover.width_px,
                "height_px": cover.height_px,
                "sha256": cover.sha256,
                "uploaded_by_member_key": (
                    str(cover.uploaded_by_user_id) if cover.uploaded_by_user_id else None
                ),
                "created_at": _json_value(cover.created_at),
                "updated_at": _json_value(cover.updated_at),
            }
        )

    data_bytes = _encoded_json(data)
    files: dict[str, dict[str, Any]] = {
        "library.json": {
            "size": len(data_bytes),
            "sha256": sha256(data_bytes).hexdigest(),
        }
    }
    for name, content in cover_files:
        files[name] = {"size": len(content), "sha256": sha256(content).hexdigest()}
    counts = {
        "members": len(members),
        **{name: len(data[name]) for name in model_groups},
        "covers": len(cover_files),
    }
    manifest = {
        "format": SERVER_LIBRARY_EXPORT_FORMAT,
        "export_format_version": SERVER_LIBRARY_EXPORT_VERSION,
        "data_schema_version": SERVER_LIBRARY_DATA_SCHEMA,
        "created_at": datetime.now(UTC).isoformat(),
        "library_name": library.name,
        "counts": counts,
        "files": files,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(destination, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        archive.writestr("manifest.json", _encoded_json(manifest))
        archive.writestr("library.json", data_bytes)
        for name, content in cover_files:
            archive.writestr(name, content)
    return manifest
