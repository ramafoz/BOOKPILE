"""Strict, read-only inspection of published BOOKPILE Local backup ZIPs."""

from __future__ import annotations

from contextlib import closing
from dataclasses import dataclass
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
from typing import Any
import zipfile

from PIL import Image, UnidentifiedImageError


LOCAL_BACKUP_FORMAT = "BOOKPILE_BACKUP"
SUPPORTED_ADAPTERS = {(1, 8): "local-v8"}
COUNTED_TABLES = (
    "bookcases",
    "shelves",
    "containers",
    "books",
    "book_authors",
    "reading_sessions",
    "loans",
)
REQUIRED_V8_TABLES = {
    *COUNTED_TABLES,
    "visual_layout_items",
    "visual_shelf_layout",
    "visual_container_layout",
}
REQUIRED_V8_VISUAL_COLUMNS = {
    "container_id",
    "x",
    "y",
    "width",
    "height",
    "row_anchor",
    "pile_support_kind",
    "pile_support_container_id",
}
REQUIRED_V8_COLUMNS = {
    "bookcases": {"id", "name", "description"},
    "shelves": {"id", "bookcase_id", "shelf_number"},
    "containers": {"id", "shelf_id", "container_type", "layer", "container_number"},
    "books": {
        "id", "title", "author", "has_multiple_authors", "isbn_10", "isbn_13",
        "subtitle", "page_count", "publisher", "current_ed_year",
        "original_publication_year", "language", "edition_number",
        "fiction_category", "binding", "publication_type", "genre_text",
        "series_name", "series_volume", "status", "goodreads_url", "notes",
        "acquisition_date", "reading_started_date", "read_date",
        "is_read_date_unknown", "is_original_collection", "cover_filename",
        "container_id", "position", "created_at", "updated_at",
    },
    "book_authors": {"book_id", "position", "name"},
    "reading_sessions": {
        "id", "book_id", "session_number", "state", "started_date",
        "finished_date", "dates_unknown", "created_at", "updated_at",
    },
    "loans": {
        "id", "book_id", "loaned_to", "notes", "state", "loaned_date",
        "expected_return_date", "returned_date", "created_at", "updated_at",
    },
    "visual_layout_items": {"item_type", "item_id", "x", "y", "width", "height"},
    "visual_shelf_layout": {"shelf_id", "height_weight"},
    "visual_container_layout": REQUIRED_V8_VISUAL_COLUMNS,
}


class LocalImportValidationError(ValueError):
    """The uploaded source cannot safely enter the canonical import pipeline."""


@dataclass(frozen=True)
class LocalArchiveLimits:
    max_archive_bytes: int = 100 * 1024 * 1024
    max_entries: int = 10_000
    max_uncompressed_bytes: int = 500 * 1024 * 1024
    max_entry_bytes: int = 100 * 1024 * 1024
    max_manifest_bytes: int = 1024 * 1024
    max_compression_ratio: int = 200


@dataclass(frozen=True)
class LocalImportInspection:
    adapter: str
    archive_sha256: str
    backup_format_version: int
    local_schema_version: int
    created_at: str
    counts: dict[str, int]
    archive_bytes: int
    uncompressed_bytes: int
    estimated_cover_bytes: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class CanonicalLocalV8Records:
    """Deterministic source-neutral records consumed by the future consolidator."""

    source_fingerprint: str
    bookcases: tuple[dict[str, Any], ...]
    shelves: tuple[dict[str, Any], ...]
    containers: tuple[dict[str, Any], ...]
    books: tuple[dict[str, Any], ...]
    contributors: tuple[dict[str, Any], ...]
    readings: tuple[dict[str, Any], ...]
    loans: tuple[dict[str, Any], ...]
    bookcase_layouts: tuple[dict[str, Any], ...]
    outside_areas: tuple[dict[str, Any], ...]
    shelf_layouts: tuple[dict[str, Any], ...]
    container_layouts: tuple[dict[str, Any], ...]


def _fail(message: str) -> None:
    raise LocalImportValidationError(message)


def _sha256_path(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_name(raw_name: str) -> str:
    path = PurePosixPath(raw_name)
    normalized = path.as_posix()
    if (
        not raw_name
        or raw_name.endswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or "\\" in raw_name
        or normalized != raw_name
    ):
        _fail(f"Unsafe ZIP entry: {raw_name or '<empty>'}")
    if normalized not in {"manifest.json", "bookpile.db"} and not (
        normalized.startswith("covers/")
        and len(path.parts) == 2
        and path.suffix.lower() == ".webp"
    ):
        _fail(f"Unexpected file in Local backup: {normalized}")
    return normalized


def _manifest(archive: zipfile.ZipFile, limits: LocalArchiveLimits) -> dict[str, Any]:
    try:
        info = archive.getinfo("manifest.json")
    except KeyError:
        _fail("The Local backup is missing manifest.json.")
    if info.file_size > limits.max_manifest_bytes:
        _fail("The Local backup manifest is unexpectedly large.")
    try:
        value = json.loads(archive.read(info).decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise LocalImportValidationError("The Local backup manifest is invalid.") from exc
    if not isinstance(value, dict):
        _fail("The Local backup manifest must be a JSON object.")
    return value


def _validated_file_manifest(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, dict) or not files:
        _fail("The Local backup manifest has no valid file list.")
    validated: dict[str, dict[str, Any]] = {}
    for raw_name, metadata in files.items():
        if not isinstance(raw_name, str) or raw_name == "manifest.json":
            _fail("The Local backup file manifest is invalid.")
        name = _safe_name(raw_name)
        if not isinstance(metadata, dict):
            _fail(f"Invalid manifest metadata for {name}.")
        size = metadata.get("size")
        checksum = metadata.get("sha256")
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            _fail(f"Invalid declared size for {name}.")
        if (
            not isinstance(checksum, str)
            or len(checksum) != 64
            or any(character not in "0123456789abcdef" for character in checksum)
        ):
            _fail(f"Invalid SHA-256 for {name}.")
        validated[name] = {"size": size, "sha256": checksum}
    if "bookpile.db" not in validated:
        _fail("The Local backup is missing bookpile.db.")
    return validated


def _check_entries(
    archive: zipfile.ZipFile,
    files: dict[str, dict[str, Any]],
    limits: LocalArchiveLimits,
) -> tuple[dict[str, zipfile.ZipInfo], int]:
    entries = archive.infolist()
    if len(entries) > limits.max_entries:
        _fail("The Local backup contains too many files.")
    by_name: dict[str, zipfile.ZipInfo] = {}
    expanded = 0
    for entry in entries:
        name = _safe_name(entry.filename)
        if name in by_name:
            _fail(f"Duplicate ZIP entry: {name}.")
        if entry.flag_bits & 0x1:
            _fail("Encrypted ZIP entries are not supported.")
        unix_kind = (entry.external_attr >> 16) & 0o170000
        if unix_kind == 0o120000:
            _fail("Symbolic links are not allowed in Local backups.")
        if entry.file_size > limits.max_entry_bytes:
            _fail(f"ZIP entry is too large: {name}.")
        if entry.file_size and (
            entry.compress_size == 0
            or entry.file_size / entry.compress_size > limits.max_compression_ratio
        ):
            _fail(f"ZIP entry has a suspicious compression ratio: {name}.")
        expanded += entry.file_size
        by_name[name] = entry
    if expanded > limits.max_uncompressed_bytes:
        _fail("The expanded Local backup is too large.")
    if set(by_name) != {"manifest.json", *files}:
        _fail("ZIP contents do not exactly match the Local backup manifest.")
    return by_name, expanded


def _extract_verified_files(
    archive: zipfile.ZipFile,
    entries: dict[str, zipfile.ZipInfo],
    files: dict[str, dict[str, Any]],
    destination: Path,
) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for name, metadata in files.items():
        target = destination.joinpath(*PurePosixPath(name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        digest = sha256()
        written = 0
        with archive.open(entries[name]) as source, target.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                output.write(chunk)
                digest.update(chunk)
                written += len(chunk)
        if written != metadata["size"] or written != entries[name].file_size:
            _fail(f"Size mismatch for {name}.")
        if digest.hexdigest() != metadata["sha256"]:
            _fail(f"Checksum mismatch for {name}.")


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        row[0]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _validate_v8_semantics(connection: sqlite3.Connection) -> None:
    invalid_author = connection.execute(
        """SELECT b.id FROM books b
           LEFT JOIN book_authors a ON a.book_id = b.id
           GROUP BY b.id
           HAVING (b.has_multiple_authors = 1 AND (b.author <> 'Multiple authors' OR COUNT(a.book_id) < 2))
               OR (b.has_multiple_authors = 0 AND COUNT(a.book_id) <> 0)
               OR COUNT(a.book_id) <> COUNT(DISTINCT a.position)
           LIMIT 1"""
    ).fetchone()
    if invalid_author:
        _fail("Local structured-author data is inconsistent.")
    for book_id, positions, names in (
        (
            book_id,
            [row[0] for row in rows],
            [" ".join(str(row[1]).split()).casefold() for row in rows],
        )
        for book_id, rows in _group_rows(
            connection.execute(
                "SELECT book_id, position, name FROM book_authors ORDER BY book_id, position"
            )
        ).items()
    ):
        if positions != list(range(1, len(positions) + 1)) or len(names) != len(set(names)):
            _fail(f"Local structured-author ordering is invalid for book {book_id}.")
    if connection.execute(
        """SELECT id FROM reading_sessions WHERE
             (state = 'ACTIVE' AND (started_date IS NULL OR finished_date IS NOT NULL OR dates_unknown <> 0))
          OR (state = 'COMPLETED' AND NOT (
                (started_date IS NOT NULL AND finished_date IS NOT NULL AND dates_unknown = 0 AND started_date <= finished_date)
             OR (started_date IS NULL AND finished_date IS NULL AND dates_unknown = 1)))
          LIMIT 1"""
    ).fetchone():
        _fail("Local reading-session dates are inconsistent.")
    if connection.execute(
        """SELECT book_id FROM reading_sessions GROUP BY book_id
           HAVING MIN(session_number) <> 1 OR MAX(session_number) <> COUNT(*)
              OR SUM(state = 'ACTIVE') > 1 OR SUM(dates_unknown = 1) > 1
           LIMIT 1"""
    ).fetchone():
        _fail("Local reading-session ordering is inconsistent.")
    if connection.execute(
        """SELECT b.id FROM books b
           LEFT JOIN reading_sessions active ON active.book_id = b.id AND active.state = 'ACTIVE'
           LEFT JOIN reading_sessions latest ON latest.book_id = b.id
             AND latest.session_number = (SELECT MAX(r.session_number) FROM reading_sessions r WHERE r.book_id = b.id)
           WHERE (active.id IS NOT NULL AND (
                    b.status <> 'CURRENTLY_READING' OR b.reading_started_date IS NOT active.started_date
                    OR b.read_date IS NOT NULL OR b.is_read_date_unknown <> 0))
              OR (active.id IS NULL AND latest.id IS NOT NULL AND (
                    b.status <> 'READ' OR b.reading_started_date IS NOT latest.started_date
                    OR b.read_date IS NOT latest.finished_date OR b.is_read_date_unknown <> latest.dates_unknown))
              OR (latest.id IS NULL AND (
                    b.status <> 'PENDING' OR b.reading_started_date IS NOT NULL
                    OR b.read_date IS NOT NULL OR b.is_read_date_unknown <> 0))
           LIMIT 1"""
    ).fetchone():
        _fail("Local reading projections do not match their session history.")
    if connection.execute(
        """SELECT id FROM loans WHERE length(trim(loaned_to)) NOT BETWEEN 1 AND 300
             OR length(COALESCE(notes, '')) > 4000 OR state NOT IN ('ACTIVE', 'RETURNED')
             OR (state = 'ACTIVE' AND returned_date IS NOT NULL)
             OR (loaned_date IS NOT NULL AND returned_date IS NOT NULL AND loaned_date > returned_date)
             OR (loaned_date IS NOT NULL AND expected_return_date IS NOT NULL AND loaned_date > expected_return_date)
           LIMIT 1"""
    ).fetchone():
        _fail("Local loan history is inconsistent.")
    if connection.execute(
        "SELECT book_id FROM loans WHERE state = 'ACTIVE' GROUP BY book_id HAVING COUNT(*) > 1 LIMIT 1"
    ).fetchone():
        _fail("A Local book has more than one active loan.")
    if connection.execute(
        """SELECT r.book_id FROM reading_sessions r JOIN loans l ON l.book_id = r.book_id
           WHERE r.state = 'ACTIVE' AND l.state = 'ACTIVE' LIMIT 1"""
    ).fetchone():
        _fail("A Local physical copy cannot be actively read and on loan simultaneously.")


def _group_rows(rows) -> dict[int, list[tuple[int, str]]]:
    grouped: dict[int, list[tuple[int, str]]] = {}
    for book_id, position, name in rows:
        grouped.setdefault(int(book_id), []).append((int(position), str(name)))
    return grouped


def _validate_database(path: Path, schema_version: int) -> tuple[dict[str, int], set[str]]:
    try:
        uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.execute("PRAGMA query_only = ON")
            integrity = connection.execute("PRAGMA integrity_check").fetchone()
            if integrity is None or integrity[0] != "ok":
                _fail("The Local catalogue failed SQLite integrity checking.")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                _fail("The Local catalogue contains broken foreign-key relationships.")
            tables = _table_names(connection)
            missing = sorted(REQUIRED_V8_TABLES - tables)
            if missing:
                _fail("The Local-v8 catalogue is missing tables: " + ", ".join(missing))
            for table, required_columns in REQUIRED_V8_COLUMNS.items():
                columns = {
                    row[1]
                    for row in connection.execute(f'PRAGMA table_info("{table}")')
                }
                missing_columns = sorted(required_columns - columns)
                if missing_columns:
                    _fail(
                        f"The Local-v8 {table} table is missing fields: "
                        + ", ".join(missing_columns)
                    )
            if "schema_migrations" in tables:
                versions = [
                    row[0]
                    for row in connection.execute(
                        "SELECT version FROM schema_migrations ORDER BY version"
                    )
                ]
                if versions != list(range(1, schema_version + 1)):
                    _fail("Manifest and SQLite schema versions do not match.")
            _validate_v8_semantics(connection)
            counts = {
                table: connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                for table in COUNTED_TABLES
            }
            covers = {
                row[0]
                for row in connection.execute(
                    "SELECT cover_filename FROM books WHERE cover_filename IS NOT NULL"
                )
            }
            if any(
                not isinstance(name, str)
                or not name
                or PurePosixPath(name).name != name
                or Path(name).suffix.lower() != ".webp"
                for name in covers
            ):
                _fail("The Local catalogue contains an unsafe cover reference.")
            return counts, covers
    except sqlite3.DatabaseError as exc:
        raise LocalImportValidationError("bookpile.db is not a valid Local SQLite catalogue.") from exc


def _validate_covers(destination: Path, files: dict[str, dict[str, Any]]) -> int:
    cover_bytes = 0
    for name, metadata in files.items():
        if not name.startswith("covers/"):
            continue
        path = destination.joinpath(*PurePosixPath(name).parts)
        try:
            with Image.open(path) as image:
                image.verify()
                if image.format != "WEBP":
                    _fail(f"Local cover is not WebP: {name}.")
        except LocalImportValidationError:
            raise
        except (UnidentifiedImageError, OSError, SyntaxError) as exc:
            raise LocalImportValidationError(f"Invalid Local cover image: {name}.") from exc
        cover_bytes += metadata["size"]
    return cover_bytes


def inspect_local_backup(
    archive_path: Path,
    extraction_directory: Path,
    *,
    limits: LocalArchiveLimits | None = None,
) -> LocalImportInspection:
    """Validate and extract one Local ZIP without touching Server persistence."""
    limits = limits or LocalArchiveLimits()
    archive_path = archive_path.resolve()
    if not archive_path.is_file():
        _fail("Choose an existing Local BOOKPILE ZIP backup.")
    archive_bytes = archive_path.stat().st_size
    if archive_bytes > limits.max_archive_bytes:
        _fail("Local BOOKPILE ZIP backups must be 100 MiB or smaller.")
    if extraction_directory.exists():
        _fail("The isolated extraction directory must not already exist.")

    try:
        with zipfile.ZipFile(archive_path) as archive:
            manifest = _manifest(archive, limits)
            if manifest.get("format") != LOCAL_BACKUP_FORMAT:
                _fail("This ZIP is not a BOOKPILE Local backup.")
            format_version = manifest.get("backup_format_version")
            schema_version = manifest.get("schema_version")
            if not isinstance(format_version, int) or not isinstance(schema_version, int):
                _fail("The Local backup has invalid source versions.")
            adapter = SUPPORTED_ADAPTERS.get((format_version, schema_version))
            if adapter is None:
                _fail(
                    "No safe importer is available for Local backup format "
                    f"{format_version}, schema {schema_version}."
                )
            created_at = manifest.get("created_at")
            if not isinstance(created_at, str) or not created_at.strip():
                _fail("The Local backup has no valid creation timestamp.")
            files = _validated_file_manifest(manifest)
            entries, expanded = _check_entries(archive, files, limits)
            try:
                _extract_verified_files(archive, entries, files, extraction_directory)
            except Exception:
                shutil.rmtree(extraction_directory, ignore_errors=True)
                raise
    except zipfile.BadZipFile as exc:
        raise LocalImportValidationError("The selected file is not a valid ZIP archive.") from exc

    try:
        counts, referenced_covers = _validate_database(
            extraction_directory / "bookpile.db", schema_version
        )
        archived_covers = {
            PurePosixPath(name).name
            for name in files
            if name.startswith("covers/")
        }
        if referenced_covers != archived_covers:
            _fail("Archived covers do not exactly match the Local catalogue references.")
        manifest_counts = manifest.get("counts")
        expected_counts = {**counts, "covers": sum(name.startswith("covers/") for name in files)}
        if manifest_counts != expected_counts:
            _fail("SQLite counts do not match the Local backup manifest.")
        cover_bytes = _validate_covers(extraction_directory, files)
    except Exception:
        shutil.rmtree(extraction_directory, ignore_errors=True)
        raise

    return LocalImportInspection(
        adapter=adapter,
        archive_sha256=_sha256_path(archive_path),
        backup_format_version=format_version,
        local_schema_version=schema_version,
        created_at=created_at,
        counts=expected_counts,
        archive_bytes=archive_bytes,
        uncompressed_bytes=expanded,
        estimated_cover_bytes=cover_bytes,
        warnings=(),
    )


def _ordered_rows(connection: sqlite3.Connection, query: str) -> tuple[dict[str, Any], ...]:
    return tuple(dict(row) for row in connection.execute(query))


def _require_finite_layout(records: tuple[dict[str, Any], ...], fields: tuple[str, ...]) -> None:
    for record in records:
        for field in fields:
            value = record[field]
            if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value):
                _fail("The Local backup contains non-finite visual geometry.")


def adapt_local_v8(extraction_directory: Path) -> CanonicalLocalV8Records:
    """Convert a previously inspected Local-v8 database into canonical records."""
    database = extraction_directory / "bookpile.db"
    if not database.is_file():
        _fail("The inspected Local-v8 database is missing.")
    uri = f"{database.resolve().as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA query_only = ON")
            bookcases = _ordered_rows(connection, "SELECT id AS source_id, name, description FROM bookcases ORDER BY id")
            shelves = _ordered_rows(connection, "SELECT id AS source_id, bookcase_id AS source_bookcase_id, shelf_number FROM shelves ORDER BY id")
            containers = _ordered_rows(connection, "SELECT id AS source_id, shelf_id AS source_shelf_id, container_type, layer, container_number FROM containers ORDER BY id")
            books = _ordered_rows(
                connection,
                """SELECT id AS source_id, title, author, isbn_10, isbn_13, subtitle,
                          page_count, publisher, current_ed_year,
                          original_publication_year, language, edition_number,
                          fiction_category, binding, publication_type, genre_text,
                          series_name, series_volume, notes, acquisition_date,
                          is_original_collection, cover_filename,
                          container_id AS source_container_id, position,
                          goodreads_url AS personal_goodreads_url,
                          created_at, updated_at
                   FROM books ORDER BY id""",
            )
            contributors = _ordered_rows(
                connection,
                """SELECT book_id AS source_book_id, 'AUTHOR' AS role_code,
                          position, name
                   FROM book_authors ORDER BY book_id, position""",
            )
            readings = _ordered_rows(
                connection,
                """SELECT id AS source_id, book_id AS source_book_id,
                          session_number, state, started_date, finished_date,
                          dates_unknown, created_at, updated_at
                   FROM reading_sessions ORDER BY book_id, session_number, id""",
            )
            loans = _ordered_rows(
                connection,
                """SELECT id AS source_id, book_id AS source_book_id, loaned_to,
                          notes, state, loaned_date, expected_return_date,
                          returned_date, created_at, updated_at
                   FROM loans ORDER BY book_id, id""",
            )
            visual_items = _ordered_rows(
                connection,
                "SELECT item_type, item_id, x, y, width, height FROM visual_layout_items ORDER BY item_type, item_id",
            )
            shelf_layouts = _ordered_rows(
                connection,
                "SELECT shelf_id AS source_shelf_id, height_weight FROM visual_shelf_layout ORDER BY shelf_id",
            )
            container_layouts = _ordered_rows(
                connection,
                """SELECT container_id AS source_container_id, x, y, width,
                          height, row_anchor, pile_support_kind,
                          pile_support_container_id AS source_support_container_id
                   FROM visual_container_layout ORDER BY container_id""",
            )
    except sqlite3.DatabaseError as exc:
        raise LocalImportValidationError("The inspected Local-v8 database cannot be adapted.") from exc

    bookcase_layouts = tuple(
        {"source_bookcase_id": item["item_id"], **{key: item[key] for key in ("x", "y", "width", "height")}}
        for item in visual_items
        if item["item_type"] == "BOOKCASE"
    )
    outside_areas = tuple(
        {
            "area_kind": "LOANED" if item["item_id"] == 1 else "READING",
            **{key: item[key] for key in ("x", "y", "width", "height")},
        }
        for item in visual_items
        if item["item_type"] == "OUTSIDE"
    )
    for records in (bookcase_layouts, outside_areas, container_layouts):
        _require_finite_layout(records, ("x", "y", "width", "height"))
    _require_finite_layout(shelf_layouts, ("height_weight",))

    canonical_payload = {
        "bookcases": bookcases,
        "shelves": shelves,
        "containers": containers,
        "books": books,
        "contributors": contributors,
        "readings": readings,
        "loans": loans,
        "bookcase_layouts": bookcase_layouts,
        "outside_areas": outside_areas,
        "shelf_layouts": shelf_layouts,
        "container_layouts": container_layouts,
    }
    fingerprint = sha256(
        json.dumps(canonical_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    ).hexdigest()
    return CanonicalLocalV8Records(source_fingerprint=fingerprint, **canonical_payload)
