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
LATEST_SCHEMA_VERSION = 4
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

ISBN_BOOK_COLUMNS = {"isbn_10", "isbn_13"}
V3_BOOK_COLUMNS = {
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
}
V4_BOOK_COLUMNS = {"has_multiple_authors"}
PRESERVED_BOOK_COLUMNS = BASELINE_BOOK_COLUMNS | ISBN_BOOK_COLUMNS


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


def _migration_3_store_bibliographic_metadata(
    connection: sqlite3.Connection,
) -> None:
    columns = table_columns(connection, "books")
    additions = (
        ("subtitle", "TEXT"),
        ("page_count", "INTEGER CHECK (page_count IS NULL OR page_count > 0)"),
        ("publisher", "TEXT"),
        (
            "current_ed_year",
            "INTEGER CHECK (current_ed_year IS NULL OR current_ed_year BETWEEN 1000 AND 9999)",
        ),
        (
            "original_publication_year",
            "INTEGER CHECK (original_publication_year IS NULL OR original_publication_year BETWEEN 1000 AND 9999)",
        ),
        ("language", "TEXT"),
        (
            "edition_number",
            "INTEGER CHECK (edition_number IS NULL OR edition_number > 0)",
        ),
        (
            "fiction_category",
            "TEXT CHECK (fiction_category IS NULL OR fiction_category IN ('FICTION', 'NON_FICTION'))",
        ),
        (
            "binding",
            "TEXT CHECK (binding IS NULL OR binding IN ('HARDCOVER', 'PAPERBACK', 'FLEXIBOUND', 'SPIRAL', 'STAPLED', 'OTHER'))",
        ),
        (
            "publication_type",
            "TEXT CHECK (publication_type IS NULL OR publication_type IN ('CONVENTIONAL_BOOK', 'COMIC_GRAPHIC_NOVEL', 'ATLAS', 'REFERENCE', 'ART_PHOTOGRAPHY_ILLUSTRATED', 'MAGAZINE_PERIODICAL', 'OTHER'))",
        ),
        ("genre_text", "TEXT"),
        ("series_name", "TEXT"),
        ("series_volume", "TEXT"),
    )
    for column, declaration in additions:
        if column not in columns:
            connection.execute(
                f'ALTER TABLE books ADD COLUMN "{column}" {declaration}'
            )


def _migration_4_store_multiple_authors(connection: sqlite3.Connection) -> None:
    columns = table_columns(connection, "books")
    if "has_multiple_authors" not in columns:
        connection.execute(
            """
            ALTER TABLE books ADD COLUMN has_multiple_authors INTEGER NOT NULL
            DEFAULT 0 CHECK (has_multiple_authors IN (0, 1))
            """
        )
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS book_authors (
            book_id INTEGER NOT NULL,
            position INTEGER NOT NULL CHECK (position > 0),
            name TEXT NOT NULL CHECK (length(trim(name)) BETWEEN 1 AND 300),
            PRIMARY KEY (book_id, position),
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_book_authors_normalized_name
        ON book_authors(book_id, lower(trim(name)));
        CREATE INDEX IF NOT EXISTS idx_book_authors_name
        ON book_authors(name COLLATE NOCASE);

        CREATE TRIGGER IF NOT EXISTS trg_multiple_authors_insert
        BEFORE INSERT ON books
        WHEN NEW.has_multiple_authors = 1
        BEGIN
            SELECT RAISE(ABORT, 'Multiple-author books must be created transactionally');
        END;

        CREATE TRIGGER IF NOT EXISTS trg_multiple_authors_update
        BEFORE UPDATE OF has_multiple_authors, author ON books
        WHEN NEW.has_multiple_authors = 1
        BEGIN
            SELECT CASE
                WHEN NEW.author <> 'Multiple authors'
                THEN RAISE(ABORT, 'Multiple-author books require author = Multiple authors')
            END;
            SELECT CASE
                WHEN (SELECT COUNT(*) FROM book_authors WHERE book_id = NEW.id) < 2
                THEN RAISE(ABORT, 'Multiple-author books require at least two authors')
            END;
        END;

        CREATE TRIGGER IF NOT EXISTS trg_multiple_authors_delete_member
        BEFORE DELETE ON book_authors
        WHEN (SELECT has_multiple_authors FROM books WHERE id = OLD.book_id) = 1
             AND (SELECT COUNT(*) FROM book_authors WHERE book_id = OLD.book_id) <= 2
        BEGIN
            SELECT RAISE(ABORT, 'Convert the book to a single author before removing this author');
        END;
        """
    )


MIGRATIONS = (
    Migration(2, "store normalized ISBN-10 and ISBN-13", _migration_2_store_isbn),
    Migration(3, "store optional bibliographic metadata", _migration_3_store_bibliographic_metadata),
    Migration(4, "store ordered multiple authors", _migration_4_store_multiple_authors),
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
    if V4_BOOK_COLUMNS <= book_columns and table_exists(connection, "book_authors"):
        return 4
    if V3_BOOK_COLUMNS <= book_columns:
        return 3
    if ISBN_BOOK_COLUMNS <= book_columns:
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


def schema_snapshot(
    connection: sqlite3.Connection,
    *,
    book_columns: set[str] | None = None,
) -> dict[str, list[dict]]:
    snapshot: dict[str, list[dict]] = {}
    selected_book_columns = book_columns or PRESERVED_BOOK_COLUMNS
    for table in BASELINE_TABLES:
        columns = [
            row["name"]
            for row in connection.execute(f'PRAGMA table_info("{table}")')
            if table != "books" or row["name"] in selected_book_columns
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
    *,
    book_columns: set[str] | None = None,
) -> str:
    integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
    if integrity != "ok":
        raise ValueError(f"SQLite integrity check failed: {integrity}")
    foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    if foreign_key_errors:
        raise ValueError("SQLite foreign-key verification failed")
    if table_exists(connection, "book_authors"):
        invalid_authors = connection.execute(
            """
            SELECT b.id
            FROM books b
            LEFT JOIN book_authors ba ON ba.book_id = b.id
            GROUP BY b.id
            HAVING
                (b.has_multiple_authors = 1 AND (
                    b.author <> 'Multiple authors' OR COUNT(ba.book_id) < 2
                ))
                OR (b.has_multiple_authors = 0 AND COUNT(ba.book_id) <> 0)
                OR COUNT(ba.book_id) <> COUNT(DISTINCT ba.position)
            LIMIT 1
            """
        ).fetchone()
        if invalid_authors:
            raise ValueError("Structured-author verification failed")
        author_rows = connection.execute(
            """
            SELECT book_id, position, name
            FROM book_authors
            ORDER BY book_id, position
            """
        ).fetchall()
        authors_by_book: dict[int, list[sqlite3.Row]] = {}
        for row in author_rows:
            authors_by_book.setdefault(row["book_id"], []).append(row)
        for rows in authors_by_book.values():
            positions = [row["position"] for row in rows]
            normalized_names = [
                " ".join(row["name"].split()).casefold() for row in rows
            ]
            if positions != list(range(1, len(rows) + 1)):
                raise ValueError("Structured-author positions are not continuous")
            if len(normalized_names) != len(set(normalized_names)):
                raise ValueError("Structured-author names contain duplicates")

    snapshot = schema_snapshot(connection, book_columns=book_columns)
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
        preserved_book_columns = BASELINE_BOOK_COLUMNS | (
            ISBN_BOOK_COLUMNS if source_version >= 2 else set()
        ) | (V3_BOOK_COLUMNS if source_version >= 3 else set())
        before_snapshot = schema_snapshot(
            connection,
            book_columns=preserved_book_columns,
        )
        before_fingerprint = verify_database(
            connection,
            before_snapshot,
            book_columns=preserved_book_columns,
        )
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

        after_fingerprint = verify_database(
            connection,
            before_snapshot,
            book_columns=preserved_book_columns,
        )
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
