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
                UNIQUE (shelf_id, layer, container_number)
            );

            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'READ')),
                goodreads_url TEXT,
                notes TEXT,
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
            """
        )
