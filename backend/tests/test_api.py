import os
from pathlib import Path

from fastapi.testclient import TestClient


TEST_DATABASE = Path(__file__).parent / "test_bookpile.db"
os.environ["BOOKPILE_DATABASE"] = str(TEST_DATABASE)

from app.main import app  # noqa: E402


def setup_function() -> None:
    TEST_DATABASE.unlink(missing_ok=True)


def teardown_function() -> None:
    TEST_DATABASE.unlink(missing_ok=True)


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
