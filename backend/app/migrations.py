import hashlib
import json
import copy
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

from .visual_geometry import (
    AuditContainer,
    ContainerKind,
    LEGACY_SUPPORT_TOLERANCE,
    Rect,
    SupportKind,
    infer_pile_support,
)


BASELINE_SCHEMA_VERSION = 1
LATEST_SCHEMA_VERSION = 8
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
PRESERVED_BOOK_COLUMNS = (
    BASELINE_BOOK_COLUMNS | ISBN_BOOK_COLUMNS | V3_BOOK_COLUMNS | V4_BOOK_COLUMNS
)


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


def _migration_5_store_reading_sessions(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS reading_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            session_number INTEGER NOT NULL CHECK (session_number > 0),
            state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'COMPLETED')),
            started_date TEXT,
            finished_date TEXT,
            dates_unknown INTEGER NOT NULL DEFAULT 0
                CHECK (dates_unknown IN (0, 1)),
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            UNIQUE (book_id, session_number),
            CHECK (
                (state = 'ACTIVE' AND started_date IS NOT NULL
                    AND finished_date IS NULL AND dates_unknown = 0)
                OR
                (state = 'COMPLETED' AND (
                    (started_date IS NOT NULL AND finished_date IS NOT NULL
                        AND dates_unknown = 0 AND started_date <= finished_date)
                    OR
                    (started_date IS NULL AND finished_date IS NULL
                        AND dates_unknown = 1)
                ))
            )
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_sessions_one_active
        ON reading_sessions(book_id) WHERE state = 'ACTIVE';
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_sessions_one_unknown
        ON reading_sessions(book_id) WHERE dates_unknown = 1;
        CREATE UNIQUE INDEX IF NOT EXISTS idx_reading_sessions_distinct_known_period
        ON reading_sessions(book_id, started_date, finished_date)
        WHERE state = 'COMPLETED' AND dates_unknown = 0;
        CREATE INDEX IF NOT EXISTS idx_reading_sessions_book
        ON reading_sessions(book_id, session_number);
        CREATE INDEX IF NOT EXISTS idx_reading_sessions_finished
        ON reading_sessions(finished_date);
        """
    )

    # v4 has exactly one projected reading record per book. Preserve it as the
    # first immutable history row; the legacy columns remain untouched.
    connection.execute(
        """
        INSERT INTO reading_sessions (
            book_id, session_number, state, started_date, finished_date,
            dates_unknown
        )
        SELECT id, 1, 'ACTIVE', reading_started_date, NULL, 0
        FROM books
        WHERE status = 'CURRENTLY_READING'
        """
    )
    connection.execute(
        """
        INSERT INTO reading_sessions (
            book_id, session_number, state, started_date, finished_date,
            dates_unknown
        )
        SELECT id, 1, 'COMPLETED', reading_started_date, read_date, 0
        FROM books
        WHERE status = 'READ' AND is_read_date_unknown = 0
        """
    )
    connection.execute(
        """
        INSERT INTO reading_sessions (
            book_id, session_number, state, started_date, finished_date,
            dates_unknown
        )
        SELECT id, 1, 'COMPLETED', NULL, NULL, 1
        FROM books
        WHERE status = 'READ' AND is_read_date_unknown = 1
        """
    )


def _migration_6_store_loan_history(connection: sqlite3.Connection) -> None:
    connection.executescript(
        """
        CREATE TABLE IF NOT EXISTS loans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            book_id INTEGER NOT NULL,
            loaned_to TEXT NOT NULL
                CHECK (length(trim(loaned_to)) BETWEEN 1 AND 300),
            notes TEXT CHECK (notes IS NULL OR length(notes) <= 4000),
            state TEXT NOT NULL CHECK (state IN ('ACTIVE', 'RETURNED')),
            loaned_date TEXT,
            expected_return_date TEXT,
            returned_date TEXT,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (book_id) REFERENCES books(id) ON DELETE CASCADE,
            CHECK (state = 'RETURNED' OR returned_date IS NULL),
            CHECK (
                loaned_date IS NULL OR returned_date IS NULL
                OR loaned_date <= returned_date
            ),
            CHECK (
                loaned_date IS NULL OR expected_return_date IS NULL
                OR loaned_date <= expected_return_date
            )
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_loans_one_active
        ON loans(book_id) WHERE state = 'ACTIVE';
        CREATE INDEX IF NOT EXISTS idx_loans_book
        ON loans(book_id, state, loaned_date, created_at);
        CREATE INDEX IF NOT EXISTS idx_loans_borrower
        ON loans(loaned_to COLLATE NOCASE);
        CREATE INDEX IF NOT EXISTS idx_loans_expected_return
        ON loans(expected_return_date) WHERE state = 'ACTIVE';
        CREATE INDEX IF NOT EXISTS idx_loans_returned
        ON loans(returned_date) WHERE state = 'RETURNED';
        """
    )


def _migration_7_center_unbounded_visual_world(
    connection: sqlite3.Connection,
) -> None:
    """Keep the legacy layout unchanged while moving its world origin to x=0."""
    connection.execute(
        """
        UPDATE visual_layout_items
        SET x = x - 50
        WHERE item_type IN ('BOOKCASE', 'OUTSIDE')
        """
    )


def _visual_audit_containers(
    connection: sqlite3.Connection,
) -> list[AuditContainer]:
    rows = connection.execute(
        """
        SELECT
            containers.id,
            containers.shelf_id,
            containers.layer,
            containers.container_type,
            visual.x,
            visual.y,
            visual.width,
            visual.height,
            (SELECT COUNT(*) FROM books
             WHERE books.container_id = containers.id) AS book_count
        FROM containers
        JOIN visual_container_layout AS visual
          ON visual.container_id = containers.id
        ORDER BY containers.id
        """
    ).fetchall()
    return [
        AuditContainer(
            id=row["id"],
            shelf_id=row["shelf_id"],
            layer=row["layer"],
            kind=ContainerKind(row["container_type"]),
            rect=Rect(row["x"], row["y"], row["width"], row["height"]),
            book_count=row["book_count"],
        )
        for row in rows
    ]


def _migration_8_store_visual_container_semantics(
    connection: sqlite3.Connection,
) -> None:
    """Store row anchors and explicit, same-layer support for every pile."""
    columns = table_columns(connection, "visual_container_layout")
    if "row_anchor" not in columns:
        connection.execute(
            """
            ALTER TABLE visual_container_layout
            ADD COLUMN row_anchor TEXT NOT NULL DEFAULT 'LEFT'
                CHECK (row_anchor IN ('LEFT', 'RIGHT'))
            """
        )
    if "pile_support_kind" not in columns:
        connection.execute(
            """
            ALTER TABLE visual_container_layout
            ADD COLUMN pile_support_kind TEXT
                CHECK (pile_support_kind IS NULL
                       OR pile_support_kind IN ('SHELF', 'ROW'))
            """
        )
    if "pile_support_container_id" not in columns:
        connection.execute(
            """
            ALTER TABLE visual_container_layout
            ADD COLUMN pile_support_container_id INTEGER
                REFERENCES containers(id) ON DELETE RESTRICT
            """
        )

    containers = _visual_audit_containers(connection)
    connection.execute(
        """
        UPDATE visual_container_layout
        SET row_anchor = 'LEFT',
            pile_support_kind = NULL,
            pile_support_container_id = NULL
        """
    )
    for pile in (item for item in containers if item.kind is ContainerKind.PILE):
        support = infer_pile_support(
            pile,
            containers,
            tolerance=LEGACY_SUPPORT_TOLERANCE,
        )
        if support.kind not in {SupportKind.SHELF, SupportKind.ROW}:
            raise ValueError(
                f"Pile {pile.id} has no unambiguous legacy support: "
                f"{support.detail}"
            )
        connection.execute(
            """
            UPDATE visual_container_layout
            SET pile_support_kind = ?, pile_support_container_id = ?
            WHERE container_id = ?
            """,
            (
                support.kind.value,
                support.container_id,
                pile.id,
            ),
        )


MIGRATIONS = (
    Migration(2, "store normalized ISBN-10 and ISBN-13", _migration_2_store_isbn),
    Migration(3, "store optional bibliographic metadata", _migration_3_store_bibliographic_metadata),
    Migration(4, "store ordered multiple authors", _migration_4_store_multiple_authors),
    Migration(5, "store complete reading history", _migration_5_store_reading_sessions),
    Migration(6, "store loan history", _migration_6_store_loan_history),
    Migration(7, "center the unbounded visual-library world", _migration_7_center_unbounded_visual_world),
    Migration(8, "store visual row anchors and pile supports", _migration_8_store_visual_container_semantics),
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
    visual_container_columns = table_columns(
        connection,
        "visual_container_layout",
    )
    if (
        V4_BOOK_COLUMNS <= book_columns
        and table_exists(connection, "book_authors")
        and table_exists(connection, "reading_sessions")
        and table_exists(connection, "loans")
        and {
            "row_anchor",
            "pile_support_kind",
            "pile_support_container_id",
        }
        <= visual_container_columns
    ):
        # A catalogue created directly by the current initializer has the
        # complete v8 schema but deliberately needs no migration ledger yet.
        return 8
    if V4_BOOK_COLUMNS <= book_columns and table_exists(connection, "book_authors"):
        if table_exists(connection, "reading_sessions"):
            if table_exists(connection, "loans"):
                return 6
            return 5
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
    tables = list(BASELINE_TABLES)
    current_version = schema_version(connection)
    if current_version >= 4 and table_exists(connection, "book_authors"):
        tables.append("book_authors")
    if current_version >= 5 and table_exists(connection, "reading_sessions"):
        tables.append("reading_sessions")
    if current_version >= 6 and table_exists(connection, "loans"):
        tables.append("loans")
    for table in tables:
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


def expected_snapshot_after_migrations(
    snapshot: dict[str, list[dict]],
    source_version: int,
    target_version: int,
) -> dict[str, list[dict]]:
    expected = copy.deepcopy(snapshot)
    if source_version < 7 <= target_version:
        for row in expected.get("visual_layout_items", []):
            if row["item_type"] in {"BOOKCASE", "OUTSIDE"}:
                row["x"] -= 50
    return expected


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
    session_schema_active = (
        table_exists(connection, "reading_sessions")
        and table_exists(connection, MIGRATION_TABLE)
        and connection.execute(
            f"SELECT COALESCE(MAX(version), 0) FROM {MIGRATION_TABLE}"
        ).fetchone()[0] >= 5
    )
    if session_schema_active:
        invalid_session = connection.execute(
            """
            SELECT id FROM reading_sessions
            WHERE
                (state = 'ACTIVE' AND (
                    started_date IS NULL OR finished_date IS NOT NULL
                    OR dates_unknown != 0
                ))
                OR
                (state = 'COMPLETED' AND NOT (
                    (started_date IS NOT NULL AND finished_date IS NOT NULL
                        AND dates_unknown = 0 AND started_date <= finished_date)
                    OR
                    (started_date IS NULL AND finished_date IS NULL
                        AND dates_unknown = 1)
                ))
            LIMIT 1
            """
        ).fetchone()
        if invalid_session:
            raise ValueError("Reading-session date verification failed")
        invalid_sequence = connection.execute(
            """
            SELECT book_id FROM reading_sessions
            GROUP BY book_id
            HAVING MIN(session_number) != 1
                OR MAX(session_number) != COUNT(*)
                OR SUM(state = 'ACTIVE') > 1
                OR SUM(dates_unknown = 1) > 1
            LIMIT 1
            """
        ).fetchone()
        if invalid_sequence:
            raise ValueError("Reading-session sequence verification failed")
        projection_error = connection.execute(
            """
            SELECT b.id
            FROM books b
            LEFT JOIN reading_sessions active
              ON active.book_id = b.id AND active.state = 'ACTIVE'
            LEFT JOIN reading_sessions latest
              ON latest.book_id = b.id
             AND latest.session_number = (
                SELECT MAX(rs.session_number)
                FROM reading_sessions rs WHERE rs.book_id = b.id
             )
            WHERE
                (active.id IS NOT NULL AND (
                    b.status != 'CURRENTLY_READING'
                    OR b.reading_started_date IS NOT active.started_date
                    OR b.read_date IS NOT NULL
                    OR b.is_read_date_unknown != 0
                ))
                OR
                (active.id IS NULL AND latest.id IS NOT NULL AND (
                    b.status != 'READ'
                    OR b.reading_started_date IS NOT latest.started_date
                    OR b.read_date IS NOT latest.finished_date
                    OR b.is_read_date_unknown != latest.dates_unknown
                ))
                OR
                (latest.id IS NULL AND (
                    b.status != 'PENDING' OR b.reading_started_date IS NOT NULL
                    OR b.read_date IS NOT NULL OR b.is_read_date_unknown != 0
                ))
            LIMIT 1
            """
        ).fetchone()
        if projection_error:
            raise ValueError("Reading-session projection verification failed")

    loan_schema_active = (
        table_exists(connection, "loans")
        and table_exists(connection, MIGRATION_TABLE)
        and connection.execute(
            f"SELECT COALESCE(MAX(version), 0) FROM {MIGRATION_TABLE}"
        ).fetchone()[0] >= 6
    )
    if loan_schema_active:
        invalid_loan = connection.execute(
            """
            SELECT id FROM loans
            WHERE length(trim(loaned_to)) NOT BETWEEN 1 AND 300
               OR length(COALESCE(notes, '')) > 4000
               OR state NOT IN ('ACTIVE', 'RETURNED')
               OR (state = 'ACTIVE' AND returned_date IS NOT NULL)
               OR (loaned_date IS NOT NULL AND returned_date IS NOT NULL
                   AND loaned_date > returned_date)
               OR (loaned_date IS NOT NULL AND expected_return_date IS NOT NULL
                   AND loaned_date > expected_return_date)
            LIMIT 1
            """
        ).fetchone()
        if invalid_loan:
            raise ValueError("Loan-history verification failed")
        multiple_active = connection.execute(
            """
            SELECT book_id FROM loans
            WHERE state = 'ACTIVE'
            GROUP BY book_id HAVING COUNT(*) > 1
            LIMIT 1
            """
        ).fetchone()
        if multiple_active:
            raise ValueError("A book has more than one active loan")

    visual_semantics_active = (
        table_exists(connection, "visual_container_layout")
        and table_exists(connection, MIGRATION_TABLE)
        and connection.execute(
            f"SELECT COALESCE(MAX(version), 0) FROM {MIGRATION_TABLE}"
        ).fetchone()[0] >= 8
    )
    if visual_semantics_active:
        invalid_visual_semantics = connection.execute(
            """
            SELECT c.id
            FROM containers AS c
            JOIN visual_container_layout AS visual
              ON visual.container_id = c.id
            LEFT JOIN containers AS support
              ON support.id = visual.pile_support_container_id
            WHERE
                visual.row_anchor NOT IN ('LEFT', 'RIGHT')
                OR (c.container_type = 'ROW' AND (
                    visual.pile_support_kind IS NOT NULL
                    OR visual.pile_support_container_id IS NOT NULL
                ))
                OR (c.container_type = 'PILE' AND (
                    visual.pile_support_kind IS NULL
                    OR (visual.pile_support_kind = 'SHELF'
                        AND visual.pile_support_container_id IS NOT NULL)
                    OR (visual.pile_support_kind = 'ROW' AND (
                        support.id IS NULL
                        OR support.container_type != 'ROW'
                        OR support.shelf_id != c.shelf_id
                        OR support.layer != c.layer
                        OR NOT EXISTS (
                            SELECT 1 FROM books
                            WHERE books.container_id = support.id
                        )
                    ))
                ))
            LIMIT 1
            """
        ).fetchone()
        if invalid_visual_semantics:
            raise ValueError("Visual container support verification failed")

    snapshot = schema_snapshot(connection, book_columns=book_columns)
    if expected_snapshot is not None:
        normalized_snapshot: dict[str, list[dict]] = {}
        for table, expected_rows in expected_snapshot.items():
            actual_rows = snapshot[table]
            if expected_rows:
                preserved_columns = tuple(expected_rows[0])
                actual_rows = [
                    {column: row[column] for column in preserved_columns}
                    for row in actual_rows
                ]
            normalized_snapshot[table] = actual_rows
        snapshot = normalized_snapshot
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
        if source_version > target_version:
            raise ValueError(
                f"Database schema v{source_version} is newer than supported v{target_version}"
            )
        preserved_book_columns = BASELINE_BOOK_COLUMNS | (
            ISBN_BOOK_COLUMNS if source_version >= 2 else set()
        ) | (V3_BOOK_COLUMNS if source_version >= 3 else set()) | (
            V4_BOOK_COLUMNS if source_version >= 4 else set()
        )
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
    expected_after_snapshot = expected_snapshot_after_migrations(
        before_snapshot,
        source_version,
        target_version,
    )
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
            expected_after_snapshot,
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
