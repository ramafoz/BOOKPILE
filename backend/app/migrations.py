import hashlib
import json
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


BASELINE_SCHEMA_VERSION = 1
LATEST_SCHEMA_VERSION = 2
MIGRATION_TABLE = "schema_migrations"

BASELINE_TABLES = (
    "bookcases",
    "shelves",
    "containers",
    "books",
    "visual_layout_items",
    "visual_shelf_layout",
    "visual_container_layout",
)

BASELINE_BOOK_COLUMNS = {
    "id",
    "title",
    "author",
    "status",
    "goodreads_url",
    "notes",
    "acquisition_date",
    "reading_started_date",
    "read_date",
    "is_read_date_unknown",
    "is_original_collection",
    "cover_filename",
    "container_id",
    "position",
    "created_at",
    "updated_at",
}


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    apply: Callable[[sqlite3.Connection], None]


@dataclass(frozen=True)
class MigrationReport:
    source_version: int
    target_version: int
    applied_versions: tuple[int, ...]
    backup_path: Path | None
    before_fingerprint: str
    after_fingerprint: str


def _migration_2_store_isbn(connection: sqlite3.Connection) -> None:
    columns = table_columns(connection, "books")
    if "isbn_10" not in columns:
        connection.execute("ALTER TABLE books ADD COLUMN isbn_10 TEXT")
    if "isbn_13" not in columns:
        connection.execute("ALTER TABLE books ADD COLUMN isbn_13 TEXT")
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_isbn_10 ON books(isbn_10)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_books_isbn_13 ON books(isbn_13)"
    )


MIGRATIONS = (
    Migration(2, "store normalized ISBN-10 and ISBN-13", _migration_2_store_isbn),
)


def connect_database(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table,),
    ).fetchone() is not None


def table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    return {
        row["name"]
        for row in connection.execute(f'PRAGMA table_info("{table}")')
    }


def infer_unversioned_schema(connection: sqlite3.Connection) -> int:
    missing_tables = [
        table for table in BASELINE_TABLES if not table_exists(connection, table)
    ]
    if missing_tables:
        raise ValueError(
            "Cannot identify the unversioned BOOKPILE schema; missing tables: "
            + ", ".join(missing_tables)
        )

    book_columns = table_columns(connection, "books")
    missing_columns = sorted(BASELINE_BOOK_COLUMNS - book_columns)
    if missing_columns:
        raise ValueError(
            "Cannot identify the unversioned BOOKPILE schema; missing book fields: "
            + ", ".join(missing_columns)
        )
    if {"isbn_10", "isbn_13"} <= book_columns:
        return 2
    return BASELINE_SCHEMA_VERSION


def schema_version(connection: sqlite3.Connection) -> int:
    if not table_exists(connection, MIGRATION_TABLE):
        return infer_unversioned_schema(connection)

    rows = connection.execute(
        f"SELECT version FROM {MIGRATION_TABLE} ORDER BY version"
    ).fetchall()
    versions = [row["version"] for row in rows]
    if not versions:
        raise ValueError("The schema migration ledger is empty")
    expected = list(range(BASELINE_SCHEMA_VERSION, max(versions) + 1))
    if versions != expected:
        raise ValueError("The schema migration ledger is incomplete or unordered")
    return versions[-1]


def schema_snapshot(connection: sqlite3.Connection) -> dict[str, list[dict]]:
    snapshot: dict[str, list[dict]] = {}
    for table in BASELINE_TABLES:
        columns = [
            row["name"]
            for row in connection.execute(f'PRAGMA table_info("{table}")')
            if table != "books" or row["name"] in BASELINE_BOOK_COLUMNS
        ]
        column_sql = ", ".join(f'"{column}"' for column in columns)
        order_sql = ", ".join(f'"{column}"' for column in columns)
        rows = connection.execute(
            f'SELECT {column_sql} FROM "{table}" ORDER BY {order_sql}'
        ).fetchall()
        snapshot[table] = [dict(row) for row in rows]
    return snapshot


def snapshot_fingerprint(snapshot: dict[str, list[dict]]) -> str:
    encoded = json.dumps(
        snapshot,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def verify_database(
    connection: sqlite3.Connection,
    expected_snapshot: dict[str, list[dict]] | None = None,
) -> str:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError(f"SQLite integrity check failed: {integrity}")
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise ValueError("SQLite foreign-key verification failed")

    snapshot = schema_snapshot(connection)
    if expected_snapshot is not None and snapshot != expected_snapshot:
        raise ValueError("Existing catalogue values changed during migration")
    return snapshot_fingerprint(snapshot)


def create_and_verify_pre_migration_backup(
    database: Path,
    covers: Path,
    backup_directory: Path,
    source_version: int,
) -> Path:
    from .exports import create_full_backup
    from .restore import extract_and_validate_archive

    backup_directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = backup_directory / (
        f"BOOKPILE-pre-migration-v{source_version}-{timestamp}.zip"
    )
    create_full_backup(
        backup,
        source_database=database,
        source_covers=covers,
        schema_version=source_version,
    )
    with tempfile.TemporaryDirectory(prefix="bookpile-migration-backup-check-") as temp:
        extract_and_validate_archive(backup, Path(temp) / "validated")
    return backup


def pending_migrations(
    source_version: int,
    target_version: int = LATEST_SCHEMA_VERSION,
) -> tuple[Migration, ...]:
    if source_version > target_version:
        raise ValueError(
            f"Database schema v{source_version} is newer than supported v{target_version}"
        )
    migrations = tuple(
        migration
        for migration in MIGRATIONS
        if source_version < migration.version <= target_version
    )
    expected_versions = tuple(range(source_version + 1, target_version + 1))
    if tuple(migration.version for migration in migrations) != expected_versions:
        raise ValueError("No complete migration path is available")
    return migrations


def run_migrations(
    database: Path,
    *,
    covers: Path,
    backup_directory: Path,
    target_version: int = LATEST_SCHEMA_VERSION,
    approved: bool = False,
) -> MigrationReport:
    database = database.resolve()
    if not database.is_file():
        raise ValueError(f"Database does not exist: {database}")

    with closing(connect_database(database)) as connection:
        source_version = schema_version(connection)
        before_snapshot = schema_snapshot(connection)
        before_fingerprint = verify_database(connection, before_snapshot)
    migrations = pending_migrations(source_version, target_version)
    if not migrations:
        return MigrationReport(
            source_version=source_version,
            target_version=target_version,
            applied_versions=(),
            backup_path=None,
            before_fingerprint=before_fingerprint,
            after_fingerprint=before_fingerprint,
        )
    if not approved:
        versions = ", ".join(str(migration.version) for migration in migrations)
        raise PermissionError(
            f"Migration approval is required before applying schema version(s): {versions}"
        )

    backup = create_and_verify_pre_migration_backup(
        database,
        covers,
        backup_directory,
        source_version,
    )

    connection = connect_database(database)
    try:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {MIGRATION_TABLE} (
                version INTEGER PRIMARY KEY CHECK (version > 0),
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for baseline_version in range(BASELINE_SCHEMA_VERSION, source_version + 1):
            if not connection.execute(
                f"SELECT 1 FROM {MIGRATION_TABLE} WHERE version = ?",
                (baseline_version,),
            ).fetchone():
                connection.execute(
                    f"INSERT INTO {MIGRATION_TABLE} (version, name) VALUES (?, ?)",
                    (baseline_version, "existing BOOKPILE schema baseline"),
                )

        for migration in migrations:
            migration.apply(connection)
            connection.execute(
                f"INSERT INTO {MIGRATION_TABLE} (version, name) VALUES (?, ?)",
                (migration.version, migration.name),
            )

        after_fingerprint = verify_database(connection, before_snapshot)
        actual_version = schema_version(connection)
        if actual_version != target_version:
            raise ValueError(
                f"Migration ended at schema v{actual_version}, expected v{target_version}"
            )
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()

    return MigrationReport(
        source_version=source_version,
        target_version=target_version,
        applied_versions=tuple(migration.version for migration in migrations),
        backup_path=backup,
        before_fingerprint=before_fingerprint,
        after_fingerprint=after_fingerprint,
    )


def copy_backup_for_rehearsal(backup: Path, destination: Path) -> tuple[Path, Path]:
    from .restore import extract_and_validate_archive

    if destination.exists():
        shutil.rmtree(destination)
    extract_and_validate_archive(backup, destination)
    return destination / "bookpile.db", destination / "covers"
