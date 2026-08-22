import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from PIL import Image

from app.database import init_database
from app.exports import create_full_backup
from app.migrations import (
    Migration,
    BASELINE_BOOK_COLUMNS,
    ISBN_BOOK_COLUMNS,
    V3_BOOK_COLUMNS,
    connect_database,
    run_migrations,
    schema_snapshot,
    schema_version,
    snapshot_fingerprint,
)
from app.restore import extract_and_validate_archive


def create_v1_catalogue(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[Path, Path, Path]:
    database = tmp_path / "data" / "bookpile.db"
    covers = database.parent / "covers"
    backups = tmp_path / "backups"
    monkeypatch.setenv("BOOKPILE_DATABASE", str(database))
    init_database()
    with sqlite3.connect(database) as connection:
        connection.execute("DROP TRIGGER trg_multiple_authors_insert")
        connection.execute("DROP TRIGGER trg_multiple_authors_update")
        connection.execute("DROP TRIGGER trg_multiple_authors_delete_member")
        connection.execute("DROP TABLE book_authors")
        connection.execute("ALTER TABLE books DROP COLUMN has_multiple_authors")
        connection.execute("DROP INDEX idx_books_isbn_10")
        connection.execute("DROP INDEX idx_books_isbn_13")
        for column in sorted(V3_BOOK_COLUMNS):
            connection.execute(f'ALTER TABLE books DROP COLUMN "{column}"')
        connection.execute("ALTER TABLE books DROP COLUMN isbn_10")
        connection.execute("ALTER TABLE books DROP COLUMN isbn_13")

    covers.mkdir(parents=True)
    cover_filename = "migration-test.webp"
    Image.new("RGB", (40, 60), "#355f52").save(
        covers / cover_filename,
        "WEBP",
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "INSERT INTO bookcases (id, name) VALUES (1, 'Migration room')"
        )
        connection.execute(
            "INSERT INTO shelves (id, bookcase_id, shelf_number) VALUES (1, 1, 1)"
        )
        connection.execute(
            """
            INSERT INTO containers (
                id, shelf_id, container_type, layer, container_number
            ) VALUES (1, 1, 'ROW', 'BACKGROUND', 1)
            """
        )
        connection.execute(
            """
            INSERT INTO books (
                id, title, author, status, acquisition_date,
                reading_started_date, read_date, cover_filename,
                container_id, position
            ) VALUES (
                1, 'Migration book', 'Careful Author', 'READ', '2025-01-01',
                '2025-01-02', '2025-01-03', ?, 1, 1
            )
            """,
            (cover_filename,),
        )
        connection.execute(
            """
            INSERT INTO visual_layout_items (
                item_type, item_id, x, y, width, height
            ) VALUES ('BOOKCASE', 1, 2, 3, 30, 70)
            """
        )
        connection.execute(
            "INSERT INTO visual_shelf_layout (shelf_id, height_weight) VALUES (1, 1.5)"
        )
        connection.execute(
            """
            INSERT INTO visual_container_layout (
                container_id, x, width, y, height
            ) VALUES (1, 5, 90, 2, 95)
            """
        )
    return database, covers, backups


def test_pending_migration_requires_explicit_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    before = database.read_bytes()

    with pytest.raises(PermissionError, match="approval is required"):
        run_migrations(
            database,
            covers=covers,
            backup_directory=backups,
        )

    assert database.read_bytes() == before
    assert not backups.exists()


def test_v1_to_v2_is_additive_backed_up_and_idempotent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    with closing(connect_database(database)) as connection:
        before_snapshot = schema_snapshot(connection)
    before_fingerprint = snapshot_fingerprint(before_snapshot)

    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=2,
    )

    assert report.source_version == 1
    assert report.target_version == 2
    assert report.applied_versions == (2,)
    assert report.before_fingerprint == before_fingerprint
    assert report.after_fingerprint == before_fingerprint
    assert report.backup_path is not None and report.backup_path.is_file()

    with closing(connect_database(database)) as connection:
        assert schema_version(connection) == 2
        columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(books)")
        }
        assert {"isbn_10", "isbn_13"} <= columns
        book = connection.execute(
            "SELECT title, isbn_10, isbn_13 FROM books WHERE id = 1"
        ).fetchone()
        assert tuple(book) == ("Migration book", None, None)
        indexes = {
            row["name"]: row["unique"]
            for row in connection.execute("PRAGMA index_list(books)")
        }
        assert indexes["idx_books_isbn_10"] == 0
        assert indexes["idx_books_isbn_13"] == 0
        assert schema_snapshot(
            connection,
            book_columns=BASELINE_BOOK_COLUMNS,
        ) == before_snapshot

    backup_count = len(list(backups.glob("*.zip")))
    second = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=2,
    )
    assert second.applied_versions == ()
    assert second.backup_path is None
    assert len(list(backups.glob("*.zip"))) == backup_count


def test_failed_migration_rolls_back_but_keeps_safety_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    before = database.read_bytes()

    def fail_after_change(connection: sqlite3.Connection) -> None:
        connection.execute("ALTER TABLE books ADD COLUMN should_rollback TEXT")
        raise RuntimeError("simulated migration failure")

    monkeypatch.setattr(
        "app.migrations.MIGRATIONS",
        (Migration(2, "simulated failure", fail_after_change),),
    )
    with pytest.raises(RuntimeError, match="simulated migration failure"):
        run_migrations(
            database,
            covers=covers,
            backup_directory=backups,
            approved=True,
            target_version=2,
        )

    with closing(connect_database(database)) as connection:
        assert schema_version(connection) == 1
        assert "should_rollback" not in {
            row["name"] for row in connection.execute("PRAGMA table_info(books)")
        }
        assert not connection.execute(
            "SELECT 1 FROM sqlite_master WHERE name = 'schema_migrations'"
        ).fetchone()
    assert database.read_bytes() == before
    assert len(list(backups.glob("*.zip"))) == 1


def test_newer_database_is_rejected_without_backup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    with sqlite3.connect(database) as connection:
        connection.execute(
            """
            CREATE TABLE schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        for version in range(1, 9):
            connection.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, f"schema {version}"),
            )

    with pytest.raises(ValueError, match="newer than supported"):
        run_migrations(
            database,
            covers=covers,
            backup_directory=backups,
            approved=True,
        )
    assert not backups.exists()


def test_backups_record_and_validate_the_schema_they_contain(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    backups.mkdir()

    v1_backup = backups / "catalogue-v1.zip"
    v1_manifest = create_full_backup(
        v1_backup,
        source_database=database,
        source_covers=covers,
    )
    v1_validation = extract_and_validate_archive(
        v1_backup,
        tmp_path / "validated-v1",
    )
    assert v1_manifest["schema_version"] == 1
    assert v1_validation["schema_version"] == 1

    run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
    )
    v7_backup = backups / "catalogue-v7.zip"
    v7_manifest = create_full_backup(
        v7_backup,
        source_database=database,
        source_covers=covers,
    )
    v7_validation = extract_and_validate_archive(
        v7_backup,
        tmp_path / "validated-v7",
    )
    assert v7_manifest["schema_version"] == 7
    assert v7_validation["schema_version"] == 7


def test_v5_to_v6_adds_empty_loan_history_without_changing_existing_data(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=5,
    )
    with closing(connect_database(database)) as connection:
        before = schema_snapshot(connection)
        before_fingerprint = snapshot_fingerprint(before)
        assert connection.execute(
            "SELECT COUNT(*) FROM reading_sessions"
        ).fetchone()[0] == 1

    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=6,
    )
    assert report.source_version == 5
    assert report.target_version == 6
    assert report.applied_versions == (6,)
    assert report.before_fingerprint == before_fingerprint
    assert report.after_fingerprint == before_fingerprint
    with closing(connect_database(database)) as connection:
        assert schema_version(connection) == 6
        assert connection.execute("SELECT COUNT(*) FROM loans").fetchone()[0] == 0
        assert connection.execute(
            "SELECT COUNT(*) FROM reading_sessions"
        ).fetchone()[0] == 1
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []


def test_v6_to_v7_centres_top_level_visual_coordinates_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=6,
    )
    with closing(connect_database(database)) as connection:
        connection.execute(
            "UPDATE visual_layout_items SET x = 54 WHERE item_type = 'OUTSIDE'"
        )
        connection.commit()
        before_books = [dict(row) for row in connection.execute("SELECT * FROM books")]
        before_items = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM visual_layout_items ORDER BY item_type, item_id"
            )
        ]

    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=7,
    )

    assert report.source_version == 6
    assert report.target_version == 7
    assert report.applied_versions == (7,)
    assert report.backup_path is not None and report.backup_path.is_file()
    with closing(connect_database(database)) as connection:
        assert schema_version(connection) == 7
        assert [dict(row) for row in connection.execute("SELECT * FROM books")] == before_books
        after_items = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM visual_layout_items ORDER BY item_type, item_id"
            )
        ]
        assert len(after_items) == len(before_items)
        for before, after in zip(before_items, after_items, strict=True):
            assert after["x"] == before["x"] - 50
            assert after["y"] == before["y"]
            assert after["width"] == before["width"]
            assert after["height"] == before["height"]

    second = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=7,
    )
    assert second.applied_versions == ()


def test_v2_to_v3_preserves_existing_isbns_and_adds_nullable_metadata(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=2,
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            "UPDATE books SET isbn_10 = ?, isbn_13 = ? WHERE id = 1",
            ("0306406152", "9780306406157"),
        )

    with closing(connect_database(database)) as connection:
        before = schema_snapshot(
            connection,
            book_columns=BASELINE_BOOK_COLUMNS | ISBN_BOOK_COLUMNS,
        )
    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=3,
    )

    assert report.source_version == 2
    assert report.target_version == 3
    assert report.applied_versions == (3,)
    assert report.before_fingerprint == report.after_fingerprint
    with closing(connect_database(database)) as connection:
        assert schema_version(connection) == 3
        assert V3_BOOK_COLUMNS <= {
            row["name"] for row in connection.execute("PRAGMA table_info(books)")
        }
        book = connection.execute("SELECT * FROM books WHERE id = 1").fetchone()
        assert book["isbn_10"] == "0306406152"
        assert book["isbn_13"] == "9780306406157"
        assert all(book[column] is None for column in V3_BOOK_COLUMNS)
        assert schema_snapshot(
            connection,
            book_columns=BASELINE_BOOK_COLUMNS | ISBN_BOOK_COLUMNS,
        ) == before


def test_v3_to_v4_preserves_author_text_without_inference(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database, covers, backups = create_v1_catalogue(tmp_path, monkeypatch)
    run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=3,
    )
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE books SET author = 'Varios' WHERE id = 1")

    with closing(connect_database(database)) as connection:
        before = schema_snapshot(
            connection,
            book_columns=BASELINE_BOOK_COLUMNS | ISBN_BOOK_COLUMNS | V3_BOOK_COLUMNS,
        )
    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
        target_version=4,
    )

    assert report.source_version == 3
    assert report.target_version == 4
    assert report.applied_versions == (4,)
    assert report.before_fingerprint == report.after_fingerprint
    with closing(connect_database(database)) as connection:
        assert schema_version(connection) == 4
        book = connection.execute(
            "SELECT author, has_multiple_authors FROM books WHERE id = 1"
        ).fetchone()
        assert tuple(book) == ("Varios", 0)
        assert connection.execute("SELECT COUNT(*) FROM book_authors").fetchone()[0] == 0
