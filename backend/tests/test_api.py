import os
import shutil
import sqlite3
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


def teardown_function() -> None:
    TEST_DATABASE.unlink(missing_ok=True)
    shutil.rmtree(TEST_DATABASE.parent / "covers", ignore_errors=True)


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
