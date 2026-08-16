import csv
import hashlib
import json
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from .database import database_path
from .migrations import LATEST_SCHEMA_VERSION, schema_version as detect_schema_version


BACKUP_FORMAT_VERSION = 1
SCHEMA_VERSION = LATEST_SCHEMA_VERSION


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_database_snapshot(
    destination: Path,
    source_database: Path | None = None,
) -> None:
    with (
        closing(sqlite3.connect(source_database or database_path())) as source,
        closing(sqlite3.connect(destination)) as target,
    ):
        source.backup(target)


def database_summary(path: Path) -> dict:
    with closing(sqlite3.connect(path)) as connection:
        connection.row_factory = sqlite3.Row
        integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
        foreign_key_errors = connection.execute(
            "PRAGMA foreign_key_check"
        ).fetchall()
        if integrity != "ok" or foreign_key_errors:
            raise ValueError("The catalogue database failed its integrity checks")

        tables = ["bookcases", "shelves", "containers", "books"]
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'book_authors'"
        ).fetchone():
            tables.append("book_authors")
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'reading_sessions'"
        ).fetchone():
            tables.append("reading_sessions")
        if connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'loans'"
        ).fetchone():
            tables.append("loans")
        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in tables
        }
        cover_filenames = [
            row["cover_filename"]
            for row in connection.execute(
                """
                SELECT cover_filename
                FROM books
                WHERE cover_filename IS NOT NULL
                ORDER BY cover_filename
                """
            )
        ]
    return {
        "integrity_check": integrity,
        "counts": counts,
        "cover_filenames": cover_filenames,
    }


def create_full_backup(
    destination: Path,
    *,
    source_database: Path | None = None,
    source_covers: Path | None = None,
    schema_version: int | None = None,
) -> dict:
    source_database = source_database or database_path()
    covers_directory = source_covers or source_database.parent / "covers"

    with tempfile.TemporaryDirectory(prefix="bookpile-backup-") as temporary:
        snapshot = Path(temporary) / "bookpile.db"
        create_database_snapshot(snapshot, source_database)
        summary = database_summary(snapshot)
        with closing(sqlite3.connect(snapshot)) as snapshot_connection:
            snapshot_connection.row_factory = sqlite3.Row
            detected_schema_version = detect_schema_version(snapshot_connection)

        files = {
            "bookpile.db": {
                "sha256": sha256_file(snapshot),
                "size": snapshot.stat().st_size,
            }
        }
        cover_paths: list[tuple[str, Path]] = []
        for filename in summary["cover_filenames"]:
            cover_path = covers_directory / filename
            if not cover_path.is_file():
                raise ValueError(
                    f"Cover referenced by the catalogue is missing: {filename}"
                )
            archive_name = f"covers/{filename}"
            files[archive_name] = {
                "sha256": sha256_file(cover_path),
                "size": cover_path.stat().st_size,
            }
            cover_paths.append((archive_name, cover_path))

        manifest = {
            "format": "BOOKPILE_BACKUP",
            "backup_format_version": BACKUP_FORMAT_VERSION,
            "schema_version": schema_version or detected_schema_version,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "integrity_check": summary["integrity_check"],
            "counts": {
                **summary["counts"],
                "covers": len(cover_paths),
            },
            "files": files,
        }

        with zipfile.ZipFile(
            destination,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=6,
        ) as archive:
            archive.write(snapshot, "bookpile.db")
            for archive_name, cover_path in cover_paths:
                archive.write(cover_path, archive_name)
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, indent=2, ensure_ascii=False),
            )
    return manifest


CSV_COLUMNS = (
    "id",
    "title",
    "author",
    "has_multiple_authors",
    "structured_authors",
    "isbn_10",
    "isbn_13",
    "subtitle",
    "page_count",
    "publisher",
    "current_ed_year",
    "original_publication_year",
    "language",
    "edition_number",
    "fiction_category",
    "binding",
    "publication_type",
    "genre_text",
    "series_name",
    "series_volume",
    "status",
    "reading_session_count",
    "loan_count",
    "active_loaned_to",
    "active_loaned_date",
    "active_expected_return_date",
    "goodreads_url",
    "notes",
    "acquisition_date",
    "reading_started_date",
    "read_date",
    "is_read_date_unknown",
    "is_original_collection",
    "bookcase",
    "shelf_number",
    "container_type",
    "layer",
    "container_number",
    "position",
    "location",
    "cover_filename",
    "created_at",
    "updated_at",
)


def write_books_csv(destination: Path) -> int:
    query = """
    SELECT
        b.id,
        b.title,
        b.author,
        b.has_multiple_authors,
        COALESCE((
            SELECT group_concat(ordered.name, ' | ')
            FROM (
                SELECT name FROM book_authors
                WHERE book_id = b.id ORDER BY position
            ) ordered
        ), '') AS structured_authors,
        b.isbn_10,
        b.isbn_13,
        b.subtitle,
        b.page_count,
        b.publisher,
        b.current_ed_year,
        b.original_publication_year,
        b.language,
        b.edition_number,
        b.fiction_category,
        b.binding,
        b.publication_type,
        b.genre_text,
        b.series_name,
        b.series_volume,
        b.status,
        (SELECT COUNT(*) FROM reading_sessions rs WHERE rs.book_id = b.id)
            AS reading_session_count,
        (SELECT COUNT(*) FROM loans loan WHERE loan.book_id = b.id)
            AS loan_count,
        (SELECT loan.loaned_to FROM loans loan
         WHERE loan.book_id = b.id AND loan.state = 'ACTIVE')
            AS active_loaned_to,
        (SELECT loan.loaned_date FROM loans loan
         WHERE loan.book_id = b.id AND loan.state = 'ACTIVE')
            AS active_loaned_date,
        (SELECT loan.expected_return_date FROM loans loan
         WHERE loan.book_id = b.id AND loan.state = 'ACTIVE')
            AS active_expected_return_date,
        b.goodreads_url,
        b.notes,
        b.acquisition_date,
        b.reading_started_date,
        b.read_date,
        b.is_read_date_unknown,
        b.is_original_collection,
        bc.name AS bookcase,
        s.shelf_number,
        c.container_type,
        c.layer,
        c.container_number,
        b.position,
        CASE
            WHEN b.container_id IS NULL THEN NULL
            ELSE bc.name || ' · Shelf ' || s.shelf_number || ' · ' ||
                 CASE c.layer
                    WHEN 'BACKGROUND' THEN 'Background'
                    ELSE 'Foreground'
                 END || ' ' ||
                 CASE c.container_type
                    WHEN 'ROW' THEN 'Row'
                    ELSE 'Pile'
                 END || ' ' || c.container_number ||
                 ' · Position ' || b.position
        END AS location,
        b.cover_filename,
        b.created_at,
        b.updated_at
    FROM books b
    LEFT JOIN containers c ON c.id = b.container_id
    LEFT JOIN shelves s ON s.id = c.shelf_id
    LEFT JOIN bookcases bc ON bc.id = s.bookcase_id
    ORDER BY b.title COLLATE NOCASE, b.author COLLATE NOCASE
    """
    with closing(sqlite3.connect(database_path())) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchall()

    with destination.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["is_original_collection"] = (
                "true" if record["is_original_collection"] else "false"
            )
            record["is_read_date_unknown"] = (
                "true" if record["is_read_date_unknown"] else "false"
            )
            record["has_multiple_authors"] = (
                "true" if record["has_multiple_authors"] else "false"
            )
            writer.writerow(record)
    return len(rows)


READING_SESSION_CSV_COLUMNS = (
    "book_id",
    "title",
    "session_number",
    "state",
    "started_date",
    "finished_date",
    "dates_unknown",
    "duration_days",
    "pages_per_day",
)


def write_reading_sessions_csv(destination: Path) -> int:
    query = """
    SELECT rs.book_id, b.title, rs.session_number, rs.state,
           rs.started_date, rs.finished_date, rs.dates_unknown,
           CASE WHEN rs.started_date IS NOT NULL AND rs.finished_date IS NOT NULL
                THEN CAST(julianday(rs.finished_date) - julianday(rs.started_date) + 1 AS INTEGER)
                ELSE NULL END AS duration_days,
           CASE WHEN b.page_count IS NOT NULL AND rs.started_date IS NOT NULL
                     AND rs.finished_date IS NOT NULL
                THEN ROUND(
                    CAST(b.page_count AS REAL) /
                    (julianday(rs.finished_date) - julianday(rs.started_date) + 1),
                    2
                )
                ELSE NULL END AS pages_per_day
    FROM reading_sessions rs
    JOIN books b ON b.id = rs.book_id
    ORDER BY b.title COLLATE NOCASE, rs.session_number
    """
    with closing(sqlite3.connect(database_path())) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchall()
    with destination.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=READING_SESSION_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            record = dict(row)
            record["dates_unknown"] = (
                "true" if record["dates_unknown"] else "false"
            )
            writer.writerow(record)
    return len(rows)


LOAN_CSV_COLUMNS = (
    "book_id",
    "title",
    "loaned_to",
    "state",
    "loaned_date",
    "expected_return_date",
    "returned_date",
    "notes",
    "created_at",
    "updated_at",
)


def write_loans_csv(destination: Path) -> int:
    query = """
    SELECT loan.book_id, b.title, loan.loaned_to, loan.state,
           loan.loaned_date, loan.expected_return_date, loan.returned_date,
           loan.notes, loan.created_at, loan.updated_at
    FROM loans loan
    JOIN books b ON b.id = loan.book_id
    ORDER BY b.title COLLATE NOCASE,
             CASE WHEN loan.state = 'ACTIVE' THEN 2
                  WHEN loan.loaned_date IS NULL THEN 0 ELSE 1 END,
             loan.loaned_date, loan.created_at, loan.id
    """
    with closing(sqlite3.connect(database_path())) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(query).fetchall()
    with destination.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=LOAN_CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(dict(row) for row in rows)
    return len(rows)
