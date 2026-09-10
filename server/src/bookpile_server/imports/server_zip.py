"""Strict inspection and adaptation of portable BOOKPILE Server libraries."""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path, PurePosixPath
import shutil
from typing import Any
from uuid import UUID
import zipfile

from PIL import Image, UnidentifiedImageError

from .local_zip import LocalArchiveLimits, LocalImportValidationError


SERVER_LIBRARY_FORMAT = "BOOKPILE_SERVER_LIBRARY"
SUPPORTED_SERVER_ADAPTERS = {(1, 1): "server-v1"}
GROUPS = (
    "bookcases", "shelves", "containers", "books", "contributors",
    "readings", "loans", "personal_book_records", "bookcase_layouts",
    "shelf_layouts", "container_layouts", "outside_areas", "covers",
)


@dataclass(frozen=True)
class ServerImportInspection:
    adapter: str
    archive_sha256: str
    export_format_version: int
    data_schema_version: int
    created_at: str
    library_name: str
    counts: dict[str, int]
    archive_bytes: int
    uncompressed_bytes: int
    estimated_cover_bytes: int
    source_members: tuple[dict[str, Any], ...]
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalServerV1Records:
    source_fingerprint: str
    library: dict[str, Any]
    members: tuple[dict[str, Any], ...]
    bookcases: tuple[dict[str, Any], ...]
    shelves: tuple[dict[str, Any], ...]
    containers: tuple[dict[str, Any], ...]
    books: tuple[dict[str, Any], ...]
    contributors: tuple[dict[str, Any], ...]
    readings: tuple[dict[str, Any], ...]
    loans: tuple[dict[str, Any], ...]
    personal_book_records: tuple[dict[str, Any], ...]
    bookcase_layouts: tuple[dict[str, Any], ...]
    shelf_layouts: tuple[dict[str, Any], ...]
    container_layouts: tuple[dict[str, Any], ...]
    outside_areas: tuple[dict[str, Any], ...]
    covers: tuple[dict[str, Any], ...]


def _fail(message: str) -> None:
    raise LocalImportValidationError(message)


def _hash_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(raw: str) -> str:
    path = PurePosixPath(raw)
    name = path.as_posix()
    if not raw or raw.endswith("/") or path.is_absolute() or ".." in path.parts or "\\" in raw or name != raw:
        _fail(f"Unsafe ZIP entry: {raw or '<empty>'}")
    if name not in {"manifest.json", "library.json"} and not (
        name.startswith("covers/") and len(path.parts) == 2 and path.suffix.lower() == ".webp"
    ):
        _fail(f"Unexpected file in Server export: {name}")
    return name


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalImportValidationError(f"The Server {label} is invalid.") from exc
    if not isinstance(value, dict):
        _fail(f"The Server {label} must be a JSON object.")
    return value


def _uuid(value: Any, label: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise LocalImportValidationError(f"Invalid Server identifier for {label}.") from exc


def _rows(data: dict[str, Any], name: str) -> tuple[dict[str, Any], ...]:
    value = data.get(name)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        _fail(f"Invalid Server data group: {name}.")
    return tuple(value)


def _ids(rows: tuple[dict[str, Any], ...], field: str, label: str) -> set[str]:
    values = {_uuid(item.get(field), f"{label}.{field}") for item in rows}
    if len(values) != len(rows):
        _fail(f"Duplicate Server identifiers in {label}.")
    return values


def _validate_relationships(records: CanonicalServerV1Records) -> None:
    source_library = _uuid(records.library.get("source_library_id"), "library")
    for group in GROUPS[:-1]:
        for row in getattr(records, group):
            if _uuid(row.get("library_id"), f"{group}.library_id") != source_library:
                _fail(f"Cross-library record in Server group: {group}.")
    bookcases = _ids(records.bookcases, "id", "bookcases")
    shelves = _ids(records.shelves, "id", "shelves")
    containers = _ids(records.containers, "id", "containers")
    books = _ids(records.books, "id", "books")
    members = {_uuid(item.get("member_key"), "members.member_key") for item in records.members}
    if len(members) != len(records.members):
        _fail("Duplicate member keys in Server export.")

    def require(rows, field: str, allowed: set[str], label: str, *, nullable: bool = False) -> None:
        for row in rows:
            value = row.get(field)
            if nullable and value is None:
                continue
            if _uuid(value, f"{label}.{field}") not in allowed:
                _fail(f"Broken Server relationship: {label}.{field}.")

    require(records.shelves, "bookcase_id", bookcases, "shelves")
    require(records.containers, "shelf_id", shelves, "containers")
    require(records.books, "container_id", containers, "books", nullable=True)
    require(records.contributors, "book_id", books, "contributors")
    require(records.readings, "book_id", books, "readings")
    require(records.readings, "user_id", members, "readings")
    require(records.loans, "book_id", books, "loans")
    require(records.personal_book_records, "book_id", books, "personal_book_records")
    require(records.personal_book_records, "user_id", members, "personal_book_records")
    require(records.bookcase_layouts, "bookcase_id", bookcases, "bookcase_layouts")
    require(records.shelf_layouts, "shelf_id", shelves, "shelf_layouts")
    require(records.container_layouts, "container_id", containers, "container_layouts")
    require(records.container_layouts, "support_container_id", containers, "container_layouts", nullable=True)
    require(records.covers, "book_id", books, "covers")
    require(records.covers, "uploaded_by_member_key", members, "covers", nullable=True)
    if len(records.bookcase_layouts) != len(records.bookcases) or len(records.shelf_layouts) != len(records.shelves) or len(records.container_layouts) != len(records.containers):
        _fail("The Server export does not contain exactly one layout for every physical object.")


def adapt_server_v1(extracted: Path) -> CanonicalServerV1Records:
    raw = (extracted / "library.json").read_bytes()
    data = _json_object(raw, "library data")
    if data.get("schema_version") != 1 or not isinstance(data.get("library"), dict):
        _fail("Unsupported Server library data schema.")
    records = CanonicalServerV1Records(
        source_fingerprint=sha256(raw).hexdigest(),
        library=data["library"],
        members=_rows(data, "members"),
        **{name: _rows(data, name) for name in GROUPS},
    )
    _validate_relationships(records)
    return records


def inspect_server_library(
    archive_path: Path,
    extracted: Path,
    *,
    limits: LocalArchiveLimits | None = None,
) -> ServerImportInspection:
    limits = limits or LocalArchiveLimits()
    archive_bytes = archive_path.stat().st_size
    if archive_bytes > limits.max_archive_bytes:
        _fail("Portable Server ZIPs must be 100 MiB or smaller.")
    if extracted.exists():
        shutil.rmtree(extracted)
    try:
        with zipfile.ZipFile(archive_path) as archive:
            entries = archive.infolist()
            if len(entries) > limits.max_entries:
                _fail("The Server export contains too many files.")
            by_name: dict[str, zipfile.ZipInfo] = {}
            expanded = 0
            for entry in entries:
                name = _safe_name(entry.filename)
                if name in by_name:
                    _fail(f"Duplicate ZIP entry: {name}.")
                if entry.flag_bits & 1 or ((entry.external_attr >> 16) & 0o170000) == 0o120000:
                    _fail("Encrypted entries and links are not supported.")
                if entry.file_size > limits.max_entry_bytes:
                    _fail(f"ZIP entry is too large: {name}.")
                if entry.file_size and (entry.compress_size == 0 or entry.file_size / entry.compress_size > limits.max_compression_ratio):
                    _fail(f"Suspicious compression ratio for {name}.")
                expanded += entry.file_size
                if expanded > limits.max_uncompressed_bytes:
                    _fail("The expanded Server export is too large.")
                by_name[name] = entry
            if "manifest.json" not in by_name or "library.json" not in by_name:
                _fail("The Server export is missing its manifest or library data.")
            if by_name["manifest.json"].file_size > limits.max_manifest_bytes:
                _fail("The Server export manifest is unexpectedly large.")
            manifest = _json_object(archive.read(by_name["manifest.json"]), "export manifest")
            version = manifest.get("export_format_version")
            schema = manifest.get("data_schema_version")
            adapter = SUPPORTED_SERVER_ADAPTERS.get((version, schema))
            if manifest.get("format") != SERVER_LIBRARY_FORMAT or adapter is None:
                _fail("No safe importer exists for this Server export version.")
            declared = manifest.get("files")
            if not isinstance(declared, dict) or set(declared) != set(by_name) - {"manifest.json"}:
                _fail("The Server export file manifest does not match the ZIP contents.")
            for name, metadata in declared.items():
                if not isinstance(metadata, dict) or not isinstance(metadata.get("size"), int) or not isinstance(metadata.get("sha256"), str):
                    _fail(f"Invalid manifest metadata for {name}.")
                content = archive.read(by_name[name])
                if len(content) != metadata["size"] or sha256(content).hexdigest() != metadata["sha256"]:
                    _fail(f"Checksum or size mismatch for {name}.")
            extracted.mkdir(parents=True, exist_ok=False)
            for name in declared:
                target = extracted.joinpath(*PurePosixPath(name).parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(by_name[name]))
    except (zipfile.BadZipFile, OSError) as exc:
        shutil.rmtree(extracted, ignore_errors=True)
        raise LocalImportValidationError("The Server export is not a readable ZIP.") from exc
    try:
        records = adapt_server_v1(extracted)
        counts = manifest.get("counts")
        if not isinstance(counts, dict):
            _fail("The Server export has invalid counts.")
        actual = {"members": len(records.members), **{name: len(getattr(records, name)) for name in GROUPS}}
        if counts != actual:
            _fail("The Server export counts do not match its data.")
        cover_bytes = 0
        cover_names: set[str] = set()
        for cover in records.covers:
            name = _safe_name(str(cover.get("archive_name", "")))
            if name in cover_names or name not in declared:
                _fail("Invalid or duplicate Server cover reference.")
            cover_names.add(name)
            path = extracted.joinpath(*PurePosixPath(name).parts)
            try:
                with Image.open(path) as image:
                    image.verify()
            except (UnidentifiedImageError, OSError) as exc:
                raise LocalImportValidationError(f"Invalid Server cover image: {name}.") from exc
            if path.stat().st_size != cover.get("byte_size") or _hash_path(path) != cover.get("sha256"):
                _fail(f"Server cover metadata mismatch: {name}.")
            cover_bytes += path.stat().st_size
        if cover_names != {name for name in declared if name.startswith("covers/")}:
            _fail("The Server export contains an unreferenced cover.")
        reading_counts: dict[str, int] = {}
        review_counts: dict[str, int] = {}
        for row in records.readings:
            key = str(row["user_id"])
            reading_counts[key] = reading_counts.get(key, 0) + 1
        for row in records.personal_book_records:
            key = str(row["user_id"])
            review_counts[key] = review_counts.get(key, 0) + 1
        source_members = tuple({
            "member_key": str(item["member_key"]),
            "username": str(item.get("username") or "Unknown member"),
            "role": str(item.get("role") or "VIEWER"),
            "reading_count": reading_counts.get(str(item["member_key"]), 0),
            "review_count": review_counts.get(str(item["member_key"]), 0),
        } for item in records.members)
        return ServerImportInspection(
            adapter=adapter,
            archive_sha256=_hash_path(archive_path),
            export_format_version=int(version),
            data_schema_version=int(schema),
            created_at=str(manifest.get("created_at", "")),
            library_name=str(manifest.get("library_name") or records.library.get("name") or "Restored library"),
            counts=actual,
            archive_bytes=archive_bytes,
            uncompressed_bytes=expanded,
            estimated_cover_bytes=cover_bytes,
            source_members=source_members,
            warnings=(),
        )
    except Exception:
        shutil.rmtree(extracted, ignore_errors=True)
        raise
