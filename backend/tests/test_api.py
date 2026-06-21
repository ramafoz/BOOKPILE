import csv
import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

from fastapi.testclient import TestClient
from PIL import Image


TEST_DATABASE = Path(__file__).parent / "test_bookpile.db"
os.environ["BOOKPILE_DATABASE"] = str(TEST_DATABASE)

from app.main import app  # noqa: E402
from app.database import init_database  # noqa: E402


def setup_function() -> None:
    TEST_DATABASE.unlink(missing_ok=True)
    shutil.rmtree(TEST_DATABASE.parent / "covers", ignore_errors=True)
    shutil.rmtree(TEST_DATABASE.parent / ".restore-staging", ignore_errors=True)


def teardown_function() -> None:
    TEST_DATABASE.unlink(missing_ok=True)
    shutil.rmtree(TEST_DATABASE.parent / "covers", ignore_errors=True)
    shutil.rmtree(TEST_DATABASE.parent / ".restore-staging", ignore_errors=True)


def test_catalogue_flow() -> None:
    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases", json={"name": "Office", "description": "North wall"}
        )
        assert bookcase.status_code == 201

        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase.json()["id"], "shelf_number": 1},
        )
        assert shelf.status_code == 201

        container = client.post(
            "/containers",
            json={
                "shelf_id": shelf.json()["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        )
        assert container.status_code == 201

        created = client.post(
            "/books",
            json={
                "title": "Piranesi",
                "author": "Susanna Clarke",
                "status": "PENDING",
                "container_id": container.json()["id"],
                "position": 3,
            },
        )
        assert created.status_code == 201
        assert created.json()["location_label"] == (
            "Office · Shelf 1 · Background Row 1 · Position 3"
        )

        stats = client.get("/stats").json()
        assert stats == {
            "total": 1,
            "pending": 1,
            "currently_reading": 0,
            "read": 0,
        }

        updated = client.patch(
            f'/books/{created.json()["id"]}', json={"status": "READ"}
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "READ"

        filtered = client.get("/books", params={"status": "READ"}).json()
        assert len(filtered) == 1

        deleted = client.delete(f'/books/{created.json()["id"]}')
        assert deleted.status_code == 204
        assert client.get("/stats").json()["total"] == 0


def test_rejects_incomplete_location() -> None:
    with TestClient(app) as client:
        response = client.post(
            "/books",
            json={"title": "Dune", "author": "Frank Herbert", "position": 2},
        )
        assert response.status_code == 422


def test_row_and_pile_can_share_number_in_same_layer() -> None:
    with TestClient(app) as client:
        bookcase = client.post("/bookcases", json={"name": "Living Room"})
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase.json()["id"], "shelf_number": 1},
        )

        row = client.post(
            "/containers",
            json={
                "shelf_id": shelf.json()["id"],
                "container_type": "ROW",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        )
        pile = client.post(
            "/containers",
            json={
                "shelf_id": shelf.json()["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        )
        duplicate_pile = client.post(
            "/containers",
            json={
                "shelf_id": shelf.json()["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        )

        assert row.status_code == 201
        assert pile.status_code == 201
        assert duplicate_pile.status_code == 409


def test_currently_reading_book_has_no_library_position() -> None:
    with TestClient(app) as client:
        bookcase = client.post("/bookcases", json={"name": "Office"})
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase.json()["id"], "shelf_number": 1},
        )
        container = client.post(
            "/containers",
            json={
                "shelf_id": shelf.json()["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        )
        book = client.post(
            "/books",
            json={
                "title": "The Left Hand of Darkness",
                "author": "Ursula K. Le Guin",
                "status": "PENDING",
                "container_id": container.json()["id"],
                "position": 1,
            },
        )

        reading = client.patch(
            f'/books/{book.json()["id"]}',
            json={"status": "CURRENTLY_READING"},
        )

        assert reading.status_code == 200
        assert reading.json()["status"] == "CURRENTLY_READING"
        assert reading.json()["container_id"] is None
        assert reading.json()["position"] is None
        assert reading.json()["reading_started_date"] == date.today().isoformat()
        assert client.get("/stats").json()["currently_reading"] == 1


def test_move_swaps_books_and_deleting_shelf_unassigns_them() -> None:
    with TestClient(app) as client:
        bookcase = client.post("/bookcases", json={"name": "Hall"})
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase.json()["id"], "shelf_number": 1},
        )
        container = client.post(
            "/containers",
            json={
                "shelf_id": shelf.json()["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        )
        first = client.post(
            "/books",
            json={
                "title": "First",
                "author": "Author",
                "container_id": container.json()["id"],
                "position": 1,
            },
        ).json()
        second = client.post(
            "/books",
            json={
                "title": "Second",
                "author": "Author",
                "container_id": container.json()["id"],
                "position": 2,
            },
        ).json()

        moved = client.post(
            f'/books/{first["id"]}/move',
            json={"container_id": container.json()["id"], "position": 2},
        )
        assert moved.status_code == 200
        books = {book["id"]: book for book in client.get("/books").json()}
        assert books[first["id"]]["position"] == 2
        assert books[second["id"]]["position"] == 1

        deleted = client.delete(f'/shelves/{shelf.json()["id"]}')
        assert deleted.status_code == 204
        books = client.get("/books").json()
        assert all(book["container_id"] is None for book in books)
        assert all(book["position"] is None for book in books)


def test_dates_can_be_entered_and_read_date_is_added_on_transition() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={
                "title": "The Dispossessed",
                "author": "Ursula K. Le Guin",
                "acquisition_date": "2026-06-01",
                "is_original_collection": False,
            },
        )
        assert created.status_code == 201
        assert created.json()["acquisition_date"] == "2026-06-01"
        assert created.json()["reading_started_date"] is None
        assert created.json()["read_date"] is None

        read = client.patch(
            f'/books/{created.json()["id"]}',
            json={"status": "READ"},
        )
        assert read.status_code == 200
        assert read.json()["read_date"] == date.today().isoformat()

        corrected = client.patch(
            f'/books/{created.json()["id"]}',
            json={
                "reading_started_date": "2026-06-10",
                "read_date": "2026-06-20",
            },
        )
        assert corrected.json()["reading_started_date"] == "2026-06-10"
        assert corrected.json()["read_date"] == "2026-06-20"


def test_existing_catalogue_migrates_without_losing_books(
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_database = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_database) as connection:
        connection.execute(
            """
            CREATE TABLE books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                author TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING'
                    CHECK (status IN ('PENDING', 'CURRENTLY_READING', 'READ')),
                goodreads_url TEXT,
                notes TEXT,
                container_id INTEGER,
                position INTEGER,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.execute(
            """
            INSERT INTO books (title, author, status)
            VALUES ('Legacy book', 'Existing author', 'PENDING')
            """
        )

    monkeypatch.setenv("BOOKPILE_DATABASE", str(legacy_database))
    init_database()

    with sqlite3.connect(legacy_database) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute("SELECT * FROM books").fetchone()
        assert row["title"] == "Legacy book"
        assert row["acquisition_date"] is None
        assert row["reading_started_date"] is None
        assert row["read_date"] is None
        assert row["is_original_collection"] == 1
        assert row["cover_filename"] is None
        assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


def test_cover_upload_is_optimized_served_and_removed() -> None:
    image_bytes = BytesIO()
    Image.new("RGB", (1800, 2400), "#8b4d36").save(image_bytes, "JPEG")

    with TestClient(app) as client:
        book = client.post(
            "/books",
            json={"title": "Kindred", "author": "Octavia E. Butler"},
        ).json()
        uploaded = client.post(
            f'/books/{book["id"]}/cover',
            files={"cover": ("kindred.jpg", image_bytes.getvalue(), "image/jpeg")},
        )

        assert uploaded.status_code == 200
        filename = uploaded.json()["cover_filename"]
        assert filename.endswith(".webp")

        served = client.get(f"/covers/{filename}")
        assert served.status_code == 200
        assert served.headers["content-type"] == "image/webp"
        with Image.open(BytesIO(served.content)) as optimized:
            assert optimized.format == "WEBP"
            assert optimized.width <= 900
            assert optimized.height <= 1400

        removed = client.delete(f'/books/{book["id"]}/cover')
        assert removed.status_code == 200
        assert removed.json()["cover_filename"] is None
        assert client.get(f"/covers/{filename}").status_code == 404


def test_cover_upload_rejects_non_image() -> None:
    with TestClient(app) as client:
        book = client.post(
            "/books",
            json={"title": "Parable", "author": "Octavia E. Butler"},
        ).json()
        response = client.post(
            f'/books/{book["id"]}/cover',
            files={"cover": ("not-image.txt", b"not an image", "text/plain")},
        )
        assert response.status_code == 415


def test_full_backup_contains_verified_database_and_covers(tmp_path: Path) -> None:
    image_bytes = BytesIO()
    Image.new("RGB", (600, 900), "#315b54").save(image_bytes, "PNG")

    with TestClient(app) as client:
        book = client.post(
            "/books",
            json={
                "title": "Beloved",
                "author": "Toni Morrison",
                "acquisition_date": "2026-06-21",
            },
        ).json()
        covered = client.post(
            f'/books/{book["id"]}/cover',
            files={"cover": ("beloved.png", image_bytes.getvalue(), "image/png")},
        ).json()

        response = client.get("/exports/full-backup")
        assert response.status_code == 200
        assert response.headers["content-type"] == "application/zip"

    archive_path = tmp_path / "backup.zip"
    archive_path.write_bytes(response.content)
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
        cover_name = f'covers/{covered["cover_filename"]}'
        assert {"manifest.json", "bookpile.db", cover_name} <= names

        manifest = json.loads(archive.read("manifest.json"))
        assert manifest["format"] == "BOOKPILE_BACKUP"
        assert manifest["backup_format_version"] == 1
        assert manifest["counts"]["books"] == 1
        assert manifest["counts"]["covers"] == 1

        for filename, metadata in manifest["files"].items():
            contents = archive.read(filename)
            assert hashlib.sha256(contents).hexdigest() == metadata["sha256"]
            assert len(contents) == metadata["size"]

        exported_database = tmp_path / "bookpile.db"
        exported_database.write_bytes(archive.read("bookpile.db"))
        with sqlite3.connect(exported_database) as connection:
            assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            exported = connection.execute(
                "SELECT title, acquisition_date, cover_filename FROM books"
            ).fetchone()
            assert exported == (
                "Beloved",
                "2026-06-21",
                covered["cover_filename"],
            )


def test_csv_export_is_excel_friendly_and_contains_location() -> None:
    with TestClient(app) as client:
        bookcase = client.post("/bookcases", json={"name": "Salón"}).json()
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 2},
        ).json()
        container = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        ).json()
        client.post(
            "/books",
            json={
                "title": "Cien años de soledad",
                "author": "Gabriel García Márquez",
                "status": "READ",
                "read_date": "2026-06-20",
                "container_id": container["id"],
                "position": 3,
            },
        )

        response = client.get("/exports/books.csv")

    assert response.status_code == 200
    assert response.content.startswith(b"\xef\xbb\xbf")
    rows = list(
        csv.DictReader(response.content.decode("utf-8-sig").splitlines())
    )
    assert len(rows) == 1
    assert rows[0]["title"] == "Cien años de soledad"
    assert rows[0]["author"] == "Gabriel García Márquez"
    assert rows[0]["read_date"] == "2026-06-20"
    assert rows[0]["bookcase"] == "Salón"
    assert rows[0]["location"] == (
        "Salón · Shelf 2 · Foreground Pile 1 · Position 3"
    )


def test_restore_recovers_deleted_book_and_cover() -> None:
    image_bytes = BytesIO()
    Image.new("RGB", (500, 800), "#4d6f78").save(image_bytes, "JPEG")

    with TestClient(app) as client:
        first = client.post(
            "/books",
            json={"title": "First backup book", "author": "Author One"},
        ).json()
        second = client.post(
            "/books",
            json={"title": "Second backup book", "author": "Author Two"},
        ).json()
        covered = client.post(
            f'/books/{second["id"]}/cover',
            files={"cover": ("cover.jpg", image_bytes.getvalue(), "image/jpeg")},
        ).json()
        backup = client.get("/exports/full-backup")
        assert backup.status_code == 200

        assert client.delete(f'/books/{second["id"]}').status_code == 204
        assert len(client.get("/books").json()) == 1

        inspection = client.post(
            "/restore/inspect",
            files={"backup": ("saved.zip", backup.content, "application/zip")},
        )
        assert inspection.status_code == 200
        assert inspection.json()["counts"]["books"] == 2
        assert inspection.json()["counts"]["covers"] == 1

        restored = client.post(f'/restore/{inspection.json()["token"]}')
        assert restored.status_code == 200
        assert restored.json()["safety_backup"].startswith("pre-restore-")

        books = client.get("/books").json()
        assert {book["title"] for book in books} == {
            "First backup book",
            "Second backup book",
        }
        restored_cover = next(
            book["cover_filename"]
            for book in books
            if book["title"] == "Second backup book"
        )
        assert restored_cover == covered["cover_filename"]
        assert client.get(f"/covers/{restored_cover}").status_code == 200

    backup_directory = TEST_DATABASE.parent.parent / "backups"
    for backup_file in backup_directory.glob("pre-restore-*.zip"):
        backup_file.unlink(missing_ok=True)


def test_restore_rejects_checksum_mismatch(tmp_path: Path) -> None:
    with TestClient(app) as client:
        client.post(
            "/books",
            json={"title": "Protected book", "author": "Safe Author"},
        )
        valid_backup = client.get("/exports/full-backup").content

    source = tmp_path / "valid.zip"
    source.write_bytes(valid_backup)
    damaged = tmp_path / "damaged.zip"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(
        damaged, "w", zipfile.ZIP_DEFLATED
    ) as replacement:
        for name in original.namelist():
            contents = original.read(name)
            if name == "bookpile.db":
                tampered = bytearray(contents)
                tampered[-1] ^= 0x01
                contents = bytes(tampered)
            replacement.writestr(name, contents)

    with TestClient(app) as client:
        response = client.post(
            "/restore/inspect",
            files={"backup": ("damaged.zip", damaged.read_bytes(), "application/zip")},
        )
        assert response.status_code == 422
        assert "Checksum mismatch" in response.json()["detail"]
        assert len(client.get("/books").json()) == 1


def test_restore_rejects_unsafe_zip_path(tmp_path: Path) -> None:
    unsafe = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(unsafe, "w") as archive:
        archive.writestr("../bookpile.db", b"no")
        archive.writestr("manifest.json", "{}")

    with TestClient(app) as client:
        response = client.post(
            "/restore/inspect",
            files={"backup": ("unsafe.zip", unsafe.read_bytes(), "application/zip")},
        )
        assert response.status_code == 422
        assert "Unsafe" in response.json()["detail"]


def test_restore_rejects_newer_schema(tmp_path: Path) -> None:
    with TestClient(app) as client:
        client.post(
            "/books",
            json={"title": "Versioned book", "author": "Version Author"},
        )
        valid_backup = client.get("/exports/full-backup").content

    source = tmp_path / "valid.zip"
    source.write_bytes(valid_backup)
    newer = tmp_path / "newer.zip"
    with zipfile.ZipFile(source) as original, zipfile.ZipFile(
        newer, "w", zipfile.ZIP_DEFLATED
    ) as replacement:
        for name in original.namelist():
            contents = original.read(name)
            if name == "manifest.json":
                manifest = json.loads(contents)
                manifest["schema_version"] = 999
                contents = json.dumps(manifest).encode()
            replacement.writestr(name, contents)

    with TestClient(app) as client:
        response = client.post(
            "/restore/inspect",
            files={"backup": ("newer.zip", newer.read_bytes(), "application/zip")},
        )
        assert response.status_code == 422
        assert "newer unsupported" in response.json()["detail"]


def test_restore_rechecks_staged_checksums() -> None:
    with TestClient(app) as client:
        client.post(
            "/books",
            json={"title": "Checksum book", "author": "Careful Author"},
        )
        backup = client.get("/exports/full-backup").content
        inspection = client.post(
            "/restore/inspect",
            files={"backup": ("backup.zip", backup, "application/zip")},
        ).json()

        staged_database = (
            TEST_DATABASE.parent
            / ".restore-staging"
            / inspection["token"]
            / "bookpile.db"
        )
        contents = bytearray(staged_database.read_bytes())
        contents[-1] ^= 0x01
        staged_database.write_bytes(contents)

        response = client.post(f'/restore/{inspection["token"]}')
        assert response.status_code == 409
        assert "checksum changed" in response.json()["detail"]
        assert len(client.get("/books").json()) == 1


def test_books_can_be_sorted_and_filtered_by_location_and_dates() -> None:
    with TestClient(app) as client:
        office = client.post("/bookcases", json={"name": "Office"}).json()
        lounge = client.post("/bookcases", json={"name": "Lounge"}).json()
        office_shelf = client.post(
            "/shelves",
            json={"bookcase_id": office["id"], "shelf_number": 2},
        ).json()
        lounge_shelf = client.post(
            "/shelves",
            json={"bookcase_id": lounge["id"], "shelf_number": 1},
        ).json()
        office_container = client.post(
            "/containers",
            json={
                "shelf_id": office_shelf["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        ).json()
        lounge_container = client.post(
            "/containers",
            json={
                "shelf_id": lounge_shelf["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 2,
            },
        ).json()

        books = [
            {
                "title": "Zulu",
                "author": "Alpha Writer",
                "acquisition_date": "2025-01-10",
                "read_date": "2025-02-01",
                "container_id": office_container["id"],
                "position": 2,
            },
            {
                "title": "Alpha",
                "author": "Zulu Writer",
                "acquisition_date": "2024-01-10",
                "read_date": "2024-02-01",
                "container_id": office_container["id"],
                "position": 1,
            },
            {
                "title": "Middle",
                "author": "Middle Writer",
                "acquisition_date": "2026-01-10",
                "container_id": lounge_container["id"],
                "position": 1,
            },
        ]
        for book in books:
            assert client.post("/books", json=book).status_code == 201

        title_desc = client.get(
            "/books",
            params={"sort_by": "title", "sort_order": "desc"},
        ).json()
        assert [book["title"] for book in title_desc] == [
            "Zulu",
            "Middle",
            "Alpha",
        ]

        author_asc = client.get(
            "/books",
            params={"sort_by": "author", "sort_order": "asc"},
        ).json()
        assert [book["author"] for book in author_asc] == [
            "Alpha Writer",
            "Middle Writer",
            "Zulu Writer",
        ]

        physical = client.get(
            "/books",
            params={"sort_by": "physical", "sort_order": "asc"},
        ).json()
        assert [book["title"] for book in physical] == [
            "Middle",
            "Alpha",
            "Zulu",
        ]

        office_books = client.get(
            "/books",
            params={"bookcase_id": office["id"], "sort_by": "physical"},
        ).json()
        assert [book["title"] for book in office_books] == ["Alpha", "Zulu"]

        exact_container = client.get(
            "/books",
            params={"container_id": lounge_container["id"]},
        ).json()
        assert [book["title"] for book in exact_container] == ["Middle"]

        acquired_2025 = client.get(
            "/books",
            params={
                "date_field": "acquisition_date",
                "date_from": "2025-01-01",
                "date_to": "2025-12-31",
            },
        ).json()
        assert [book["title"] for book in acquired_2025] == ["Zulu"]

        read_desc = client.get(
            "/books",
            params={"sort_by": "read_date", "sort_order": "desc"},
        ).json()
        assert [book["title"] for book in read_desc] == [
            "Zulu",
            "Alpha",
            "Middle",
        ]

        invalid_dates = client.get(
            "/books",
            params={"date_from": "2026-01-01", "date_to": "2025-01-01"},
        )
        assert invalid_dates.status_code == 422


def test_occupied_position_can_shift_contiguous_books_to_make_room() -> None:
    with TestClient(app) as client:
        bookcase = client.post("/bookcases", json={"name": "Shift Test"}).json()
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 1},
        ).json()
        container = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        ).json()
        other_container = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        ).json()

        for position in (1, 2, 3, 5):
            response = client.post(
                "/books",
                json={
                    "title": f"Existing {position}",
                    "author": "Author",
                    "container_id": container["id"],
                    "position": position,
                },
            )
            assert response.status_code == 201
        other = client.post(
            "/books",
            json={
                "title": "Other container",
                "author": "Author",
                "container_id": other_container["id"],
                "position": 2,
            },
        ).json()

        conflict = client.post(
            "/books",
            json={
                "title": "Inserted",
                "author": "New Author",
                "container_id": container["id"],
                "position": 2,
            },
        )
        assert conflict.status_code == 409
        detail = conflict.json()["detail"]
        assert detail["code"] == "POSITION_OCCUPIED"
        assert detail["occupant"]["title"] == "Existing 2"
        assert detail["shift_count"] == 2
        assert detail["last_position"] == 3

        before_retry = client.get(
            "/books",
            params={"container_id": container["id"], "sort_by": "physical"},
        ).json()
        assert [(book["title"], book["position"]) for book in before_retry] == [
            ("Existing 1", 1),
            ("Existing 2", 2),
            ("Existing 3", 3),
            ("Existing 5", 5),
        ]

        inserted = client.post(
            "/books",
            json={
                "title": "Inserted",
                "author": "New Author",
                "container_id": container["id"],
                "position": 2,
                "shift_existing": True,
            },
        )
        assert inserted.status_code == 201

        shifted = client.get(
            "/books",
            params={"container_id": container["id"], "sort_by": "physical"},
        ).json()
        assert [(book["title"], book["position"]) for book in shifted] == [
            ("Existing 1", 1),
            ("Inserted", 2),
            ("Existing 2", 3),
            ("Existing 3", 4),
            ("Existing 5", 5),
        ]

        untouched = next(
            book
            for book in client.get(
                "/books",
                params={"container_id": other_container["id"]},
            ).json()
            if book["id"] == other["id"]
        )
        assert untouched["position"] == 2


def test_shift_at_end_extends_container_positions() -> None:
    with TestClient(app) as client:
        bookcase = client.post("/bookcases", json={"name": "End Shift"}).json()
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 1},
        ).json()
        container = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        ).json()
        for position in range(1, 9):
            client.post(
                "/books",
                json={
                    "title": f"Book {position}",
                    "author": "Author",
                    "container_id": container["id"],
                    "position": position,
                },
            )

        inserted = client.post(
            "/books",
            json={
                "title": "New Seven",
                "author": "Author",
                "container_id": container["id"],
                "position": 7,
                "shift_existing": True,
            },
        )
        assert inserted.status_code == 201
        books = client.get(
            "/books",
            params={"container_id": container["id"], "sort_by": "physical"},
        ).json()
        positions = {book["title"]: book["position"] for book in books}
        assert positions["New Seven"] == 7
        assert positions["Book 7"] == 8
        assert positions["Book 8"] == 9


def test_library_map_returns_ordered_hierarchy_books_and_status_counts() -> None:
    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases", json={"name": "Visual Bookcase"}
        ).json()
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 1},
        ).json()
        background = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        ).json()
        foreground = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        ).json()
        client.post(
            "/books",
            json={
                "title": "Background pending",
                "author": "Author",
                "status": "PENDING",
                "container_id": background["id"],
                "position": 2,
            },
        )
        client.post(
            "/books",
            json={
                "title": "Foreground read",
                "author": "Author",
                "status": "READ",
                "container_id": foreground["id"],
                "position": 1,
            },
        )
        reading = client.post(
            "/books",
            json={
                "title": "Reading away from shelf",
                "author": "Author",
                "status": "CURRENTLY_READING",
            },
        ).json()

        response = client.get("/library-map")
        assert response.status_code == 200
        payload = response.json()
        mapped = payload["bookcases"][0]
        assert mapped["name"] == "Visual Bookcase"
        assert mapped["book_count"] == 2
        mapped_shelf = mapped["shelves"][0]
        assert mapped_shelf["book_count"] == 2
        assert [container["layer"] for container in mapped_shelf["containers"]] == [
            "BACKGROUND",
            "FOREGROUND",
        ]
        assert mapped_shelf["containers"][0]["books"][0]["position"] == 2
        assert mapped_shelf["containers"][0]["status_counts"] == {
            "pending": 1,
            "reading": 0,
            "read": 0,
        }
        assert mapped_shelf["containers"][1]["status_counts"]["read"] == 1
        assert payload["outside_books"] == [
            {
                "id": reading["id"],
                "title": "Reading away from shelf",
                "status": "CURRENTLY_READING",
                "position": None,
            }
        ]
        assert len(payload["layout"]["bookcases"]) == 1
        assert payload["layout"]["bookcases"][0]["id"] == mapped["id"]
        assert payload["layout"]["shelves"] == [
            {"id": mapped_shelf["id"], "height_weight": 1.0}
        ]
        assert len(payload["layout"]["containers"]) == 2

        layout = payload["layout"]
        layout["bookcases"][0].update(
            {"x": 11, "y": 9, "width": 35, "height": 70}
        )
        layout["shelves"][0]["height_weight"] = 2.5
        layout["containers"][0].update({"x": 8, "width": 40})
        saved = client.put("/visual-layout", json=layout)
        assert saved.status_code == 200
        assert saved.json()["bookcases"][0]["x"] == 11
        assert saved.json()["shelves"][0]["height_weight"] == 2.5
        assert saved.json()["containers"][0]["x"] == 8

        persisted = client.get("/library-map").json()["layout"]
        assert persisted == saved.json()

        invalid = persisted.copy()
        invalid["bookcases"] = [
            {**invalid["bookcases"][0], "x": 90, "width": 35}
        ]
        assert client.put("/visual-layout", json=invalid).status_code == 422
