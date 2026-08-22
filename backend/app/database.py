import os
import sqlite3
from pathlib import Path


DEFAULT_DATABASE_PATH = Path(__file__).resolve().parent.parent / "data" / "bookpile.db"


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def database_path() -> Path:
    return Path(os.getenv("BOOKPILE_DATABASE", DEFAULT_DATABASE_PATH))


def connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_database() -> None:
    with connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS bookcases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                description TEXT
            );

            CREATE TABLE IF NOT EXISTS shelves (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                bookcase_id INTEGER NOT NULL,
                shelf_number INTEGER NOT NULL CHECK (shelf_number > 0),
                FOREIGN KEY (bookcase_id) REFERENCES bookcases(id) ON DELETE CASCADE,
                UNIQUE (bookcase_id, shelf_number)
            );

            CREATE TABLE IF NOT EXISTS containers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelf_id INTEGER NOT NULL,
                container_type TEXT NOT NULL CHECK (container_type IN ('ROW', 'PILE')),
                layer TEXT NOT NULL CHECK (layer IN ('BACKGROUND', 'FOREGROUND')),
                container_number INTEGER NOT NULL CHECK (container_number > 0),
                FOREIGN KEY (shelf_id) REFERENCES shelves(id) ON DELETE CASCADE,
                UNIQUE (shelf_id, container_type, layer, container_number)
            );

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                has_multiple_authors INTEGER NOT NULL DEFAULT 0
                    CHECK (has_multiple_authors IN (0, 1)),
                isbn_10 TEXT,
                isbn_13 TEXT,
                subtitle TEXT,
                page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
                publisher TEXT,
                current_ed_year INTEGER CHECK (
                    current_ed_year IS NULL OR current_ed_year BETWEEN 1000 AND 9999
                ),
                original_publication_year INTEGER CHECK (
                    original_publication_year IS NULL
                    OR original_publication_year BETWEEN 1000 AND 9999
                ),
                language TEXT,
                edition_number INTEGER CHECK (
                    edition_number IS NULL OR edition_number > 0
                ),
                fiction_category TEXT CHECK (
                    fiction_category IS NULL
                    OR fiction_category IN ('FICTION', 'NON_FICTION')
                ),
                binding TEXT CHECK (
                    binding IS NULL OR binding IN (
                        'HARDCOVER', 'PAPERBACK', 'FLEXIBOUND',
                        'SPIRAL', 'STAPLED', 'OTHER'
                    )
                ),
                publication_type TEXT CHECK (
                    publication_type IS NULL OR publication_type IN (
                        'CONVENTIONAL_BOOK', 'COMIC_GRAPHIC_NOVEL', 'ATLAS',
                        'REFERENCE', 'ART_PHOTOGRAPHY_ILLUSTRATED',
                        'MAGAZINE_PERIODICAL', 'OTHER'
                    )
                ),
                genre_text TEXT,
                series_name TEXT,
                series_volume TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'CURRENTLY_READING', 'READ')),
                goodreads_url TEXT,
                notes TEXT,
                acquisition_date TEXT,
                reading_started_date TEXT,
                read_date TEXT,
                is_read_date_unknown INTEGER NOT NULL DEFAULT 0
                    CHECK (is_read_date_unknown IN (0, 1)),
                is_original_collection INTEGER NOT NULL DEFAULT 0
                    CHECK (is_original_collection IN (0, 1)),
                cover_filename TEXT,
                container_id INTEGER,
                position INTEGER CHECK (position IS NULL OR position > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (container_id) REFERENCES containers(id) ON DELETE SET NULL,
                CHECK (
                    (container_id IS NULL AND position IS NULL)
                    OR (container_id IS NOT NULL AND position IS NOT NULL)
                ),
                UNIQUE (container_id, position)
            );

            CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
            CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
            CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);

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

            CREATE TABLE IF NOT EXISTS visual_layout_items (
                item_type TEXT NOT NULL
                    CHECK (item_type IN ('BOOKCASE', 'OUTSIDE')),
                item_id INTEGER NOT NULL DEFAULT 0,
                x REAL NOT NULL,
                y REAL NOT NULL,
                width REAL NOT NULL,
                height REAL NOT NULL,
                PRIMARY KEY (item_type, item_id)
            );

            CREATE TABLE IF NOT EXISTS visual_shelf_layout (
                shelf_id INTEGER PRIMARY KEY,
                height_weight REAL NOT NULL DEFAULT 1
                    CHECK (height_weight > 0),
                FOREIGN KEY (shelf_id) REFERENCES shelves(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS visual_container_layout (
                container_id INTEGER PRIMARY KEY,
                x REAL NOT NULL,
                width REAL NOT NULL,
                y REAL NOT NULL DEFAULT 0,
                height REAL NOT NULL DEFAULT 100,
                row_anchor TEXT NOT NULL DEFAULT 'LEFT'
                    CHECK (row_anchor IN ('LEFT', 'RIGHT')),
                pile_support_kind TEXT
                    CHECK (pile_support_kind IS NULL
                           OR pile_support_kind IN ('SHELF', 'ROW')),
                pile_support_container_id INTEGER,
                FOREIGN KEY (container_id) REFERENCES containers(id) ON DELETE CASCADE,
                FOREIGN KEY (pile_support_container_id)
                    REFERENCES containers(id) ON DELETE RESTRICT
            );
            """
        )
        _migrate_container_numbering(connection)
        _migrate_book_statuses(connection)
        _migrate_book_dates(connection)
        _migrate_book_covers(connection)
        _migrate_visual_container_layout(connection)
        book_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(books)")
        }
        if {"isbn_10", "isbn_13"} <= book_columns:
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_books_isbn_10 ON books(isbn_10)"
            )
            connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_books_isbn_13 ON books(isbn_13)"
            )


def _migrate_visual_container_layout(connection: sqlite3.Connection) -> None:
    """Allow each visual container to keep its own vertical placement and height."""
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(visual_container_layout)")
    }
    added_vertical_layout = False
    if "y" not in columns:
        connection.execute(
            "ALTER TABLE visual_container_layout ADD COLUMN y REAL NOT NULL DEFAULT 0"
        )
        added_vertical_layout = True
    if "height" not in columns:
        connection.execute(
            """
            ALTER TABLE visual_container_layout
            ADD COLUMN height REAL NOT NULL DEFAULT 100
            """
        )
        added_vertical_layout = True
    if added_vertical_layout:
        _set_default_visual_container_heights(connection)


def _set_default_visual_container_heights(connection: sqlite3.Connection) -> None:
    """Give old overlapping shelf layers a readable default split."""
    connection.execute(
        """
        UPDATE visual_container_layout
        SET y = 0, height = 68
        WHERE y = 0
          AND height = 100
          AND container_id IN (
              SELECT background.id
              FROM containers AS background
              WHERE background.layer = 'BACKGROUND'
                AND EXISTS (
                    SELECT 1
                    FROM containers AS foreground
                    WHERE foreground.shelf_id = background.shelf_id
                      AND foreground.layer = 'FOREGROUND'
                )
          )
        """
    )
    connection.execute(
        """
        UPDATE visual_container_layout
        SET y = 50, height = 50
        WHERE y = 0
          AND height = 100
          AND container_id IN (
              SELECT foreground.id
              FROM containers AS foreground
              WHERE foreground.layer = 'FOREGROUND'
                AND EXISTS (
                    SELECT 1
                    FROM containers AS background
                    WHERE background.shelf_id = foreground.shelf_id
                      AND background.layer = 'BACKGROUND'
                )
          )
        """
    )


def _migrate_container_numbering(connection: sqlite3.Connection) -> None:
    """Allow a row and a pile to use the same number within one shelf/layer."""
    table_sql_row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'containers'
        """
    ).fetchone()
    if table_sql_row is None:
        return

    normalized_sql = " ".join(table_sql_row["sql"].lower().split())
    expected_constraint = "unique (shelf_id, container_type, layer, container_number)"
    if expected_constraint in normalized_sql:
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            BEGIN;

            CREATE TABLE containers_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                shelf_id INTEGER NOT NULL,
                container_type TEXT NOT NULL CHECK (container_type IN ('ROW', 'PILE')),
                layer TEXT NOT NULL CHECK (layer IN ('BACKGROUND', 'FOREGROUND')),
                container_number INTEGER NOT NULL CHECK (container_number > 0),
                FOREIGN KEY (shelf_id) REFERENCES shelves(id) ON DELETE CASCADE,
                UNIQUE (shelf_id, container_type, layer, container_number)
            );

            INSERT INTO containers_new (
                id, shelf_id, container_type, layer, container_number
            )
            SELECT id, shelf_id, container_type, layer, container_number
            FROM containers;

            DROP TABLE containers;
            ALTER TABLE containers_new RENAME TO containers;

            COMMIT;
            """
        )
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _migrate_book_statuses(connection: sqlite3.Connection) -> None:
    """Add CURRENTLY_READING while preserving the existing catalogue."""
    table_sql_row = connection.execute(
        """
        SELECT sql
        FROM sqlite_master
        WHERE type = 'table' AND name = 'books'
        """
    ).fetchone()
    if table_sql_row is None:
        return

    normalized_sql = " ".join(table_sql_row["sql"].lower().split())
    if "'currently_reading'" in normalized_sql:
        return

    connection.execute("PRAGMA foreign_keys = OFF")
    try:
        connection.executescript(
            """
            BEGIN;

            CREATE TABLE books_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                has_multiple_authors INTEGER NOT NULL DEFAULT 0
                    CHECK (has_multiple_authors IN (0, 1)),
                isbn_10 TEXT,
                isbn_13 TEXT,
                subtitle TEXT,
                page_count INTEGER CHECK (page_count IS NULL OR page_count > 0),
                publisher TEXT,
                current_ed_year INTEGER CHECK (
                    current_ed_year IS NULL OR current_ed_year BETWEEN 1000 AND 9999
                ),
                original_publication_year INTEGER CHECK (
                    original_publication_year IS NULL
                    OR original_publication_year BETWEEN 1000 AND 9999
                ),
                language TEXT,
                edition_number INTEGER CHECK (
                    edition_number IS NULL OR edition_number > 0
                ),
                fiction_category TEXT CHECK (
                    fiction_category IS NULL
                    OR fiction_category IN ('FICTION', 'NON_FICTION')
                ),
                binding TEXT CHECK (
                    binding IS NULL OR binding IN (
                        'HARDCOVER', 'PAPERBACK', 'FLEXIBOUND',
                        'SPIRAL', 'STAPLED', 'OTHER'
                    )
                ),
                publication_type TEXT CHECK (
                    publication_type IS NULL OR publication_type IN (
                        'CONVENTIONAL_BOOK', 'COMIC_GRAPHIC_NOVEL', 'ATLAS',
                        'REFERENCE', 'ART_PHOTOGRAPHY_ILLUSTRATED',
                        'MAGAZINE_PERIODICAL', 'OTHER'
                    )
                ),
                genre_text TEXT,
                series_name TEXT,
                series_volume TEXT,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'CURRENTLY_READING', 'READ')),
                goodreads_url TEXT,
                notes TEXT,
                acquisition_date TEXT,
                reading_started_date TEXT,
                read_date TEXT,
                is_read_date_unknown INTEGER NOT NULL DEFAULT 0
                    CHECK (is_read_date_unknown IN (0, 1)),
                is_original_collection INTEGER NOT NULL DEFAULT 0
                    CHECK (is_original_collection IN (0, 1)),
                cover_filename TEXT,
                container_id INTEGER,
                position INTEGER CHECK (position IS NULL OR position > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (container_id) REFERENCES containers(id) ON DELETE SET NULL,
                CHECK (
                    (container_id IS NULL AND position IS NULL)
                    OR (container_id IS NOT NULL AND position IS NOT NULL)
                ),
                UNIQUE (container_id, position)
            );

            INSERT INTO books_new (
                id, title, author, has_multiple_authors, isbn_10, isbn_13,
                subtitle, page_count, publisher, current_ed_year,
                original_publication_year, language, edition_number,
                fiction_category, binding, publication_type, genre_text,
                series_name, series_volume, status, goodreads_url, notes,
                acquisition_date, reading_started_date, read_date,
                is_read_date_unknown, is_original_collection, cover_filename,
                container_id, position, created_at, updated_at
            )
            SELECT
                id, title, author, 0, NULL, NULL,
                NULL, NULL, NULL, NULL, NULL, NULL, NULL,
                NULL, NULL, NULL, NULL, NULL, NULL,
                status, goodreads_url, notes,
                NULL, NULL, NULL, 0, 1, NULL,
                container_id, position, created_at, updated_at
            FROM books;

            DROP TABLE books;
            ALTER TABLE books_new RENAME TO books;

            CREATE INDEX IF NOT EXISTS idx_books_status ON books(status);
            CREATE INDEX IF NOT EXISTS idx_books_title ON books(title);
            CREATE INDEX IF NOT EXISTS idx_books_author ON books(author);
            CREATE INDEX IF NOT EXISTS idx_books_isbn_10 ON books(isbn_10);
            CREATE INDEX IF NOT EXISTS idx_books_isbn_13 ON books(isbn_13);

            COMMIT;
            """
        )
    except Exception:
        if connection.in_transaction:
            connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")


def _migrate_book_dates(connection: sqlite3.Connection) -> None:
    """Add optional lifecycle dates without changing existing book data."""
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(books)").fetchall()
    }
    was_existing_catalogue = "acquisition_date" not in columns

    additions = (
        ("acquisition_date", "TEXT"),
        ("reading_started_date", "TEXT"),
        ("read_date", "TEXT"),
        (
            "is_read_date_unknown",
            "INTEGER NOT NULL DEFAULT 0 CHECK (is_read_date_unknown IN (0, 1))",
        ),
        (
            "is_original_collection",
            "INTEGER NOT NULL DEFAULT 0 CHECK (is_original_collection IN (0, 1))",
        ),
    )
    for column, declaration in additions:
        if column not in columns:
            connection.execute(
                f"ALTER TABLE books ADD COLUMN {column} {declaration}"
            )

    if was_existing_catalogue:
        connection.execute(
            "UPDATE books SET is_original_collection = 1"
        )


def _migrate_book_covers(connection: sqlite3.Connection) -> None:
    columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(books)").fetchall()
    }
    if "cover_filename" not in columns:
        connection.execute("ALTER TABLE books ADD COLUMN cover_filename TEXT")
