import sqlite3
from contextlib import closing
from pathlib import Path

import pytest
from PIL import Image

from app.database import init_database
from app.exports import create_full_backup
from app.migrations import (
    Migration,
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
        connection.execute("DROP INDEX idx_books_isbn_10")
        connection.execute("DROP INDEX idx_books_isbn_13")
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
        assert schema_snapshot(connection) == before_snapshot

    backup_count = len(list(backups.glob("*.zip")))
    second = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
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
        for version in range(1, 4):
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
    v2_backup = backups / "catalogue-v2.zip"
    v2_manifest = create_full_backup(
        v2_backup,
        source_database=database,
        source_covers=covers,
    )
    v2_validation = extract_and_validate_archive(
        v2_backup,
        tmp_path / "validated-v2",
    )
    assert v2_manifest["schema_version"] == 2
    assert v2_validation["schema_version"] == 2
