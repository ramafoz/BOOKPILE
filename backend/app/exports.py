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


BACKUP_FORMAT_VERSION = 1
SCHEMA_VERSION = 1


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_database_snapshot(destination: Path) -> None:
    with (
        closing(sqlite3.connect(database_path())) as source,
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

        counts = {
            table: connection.execute(
                f"SELECT COUNT(*) FROM {table}"
            ).fetchone()[0]
            for table in ("bookcases", "shelves", "containers", "books")
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


def create_full_backup(destination: Path) -> dict:
    data_directory = database_path().parent
    covers_directory = data_directory / "covers"

    with tempfile.TemporaryDirectory(prefix="bookpile-backup-") as temporary:
        snapshot = Path(temporary) / "bookpile.db"
        create_database_snapshot(snapshot)
        summary = database_summary(snapshot)

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
            "schema_version": SCHEMA_VERSION,
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
    "status",
    "goodreads_url",
    "notes",
    "acquisition_date",
    "reading_started_date",
    "read_date",
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
        b.status,
        b.goodreads_url,
        b.notes,
        b.acquisition_date,
        b.reading_started_date,
        b.read_date,
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
            writer.writerow(record)
    return len(rows)
