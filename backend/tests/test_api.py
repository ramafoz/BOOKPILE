import csv
import hashlib
import json
import os
import shutil
import sqlite3
import zipfile
from contextlib import closing
from unittest.mock import patch
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image


TEST_DATABASE = Path(__file__).parent / "test_bookpile.db"
os.environ["BOOKPILE_DATABASE"] = str(TEST_DATABASE)

from app.main import app  # noqa: E402
from app.database import init_database  # noqa: E402
from app.migrations import connect_database, schema_version  # noqa: E402


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
            "currently_rereading": 0,
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


def test_isbn_lookup_endpoint_is_read_only_and_normalized() -> None:
    candidate = {
        "source": "OPEN_LIBRARY",
        "source_record_id": "OL1M",
        "identifiers": {"isbn_10": "0306406152", "isbn_13": "9780306406157"},
        "title": "Example Book",
        "subtitle": None,
        "authors": ["Example Author"],
        "publisher": None,
        "published_date": None,
        "page_count": None,
        "subjects": [],
        "language": None,
        "edition": None,
        "genres": [],
        "category": None,
        "format": None,
        "confidence_or_match_notes": None,
    }
    with patch("app.main.lookup_isbn", return_value=[candidate]) as lookup:
        with TestClient(app) as client:
            before = client.get("/stats").json()
            response = client.get(
                "/bibliography/isbn", params={"isbn": "978-0-306-40615-7"}
            )
            after = client.get("/stats").json()

    assert response.status_code == 200
    assert response.json()["isbn"] == "9780306406157"
    assert response.json()["candidates"][0]["title"] == "Example Book"
    lookup.assert_called_once_with("9780306406157")
    assert before == after


def test_book_isbns_are_normalized_editable_searchable_and_not_unique() -> None:
    with TestClient(app) as client:
        first = client.post(
            "/books",
            json={
                "title": "ISBN edition one",
                "author": "Identifier Author",
                "isbn_10": "0-306-40615-2",
                "isbn_13": "978-0-306-40615-7",
                "subtitle": "A metadata export",
                "page_count": 320,
                "publisher": "Example Press",
                "current_ed_year": 2024,
                "original_publication_year": 1967,
                "language": "Spanish",
                "edition_number": 2,
                "fiction_category": "FICTION",
                "binding": "PAPERBACK",
                "publication_type": "CONVENTIONAL_BOOK",
                "genre_text": "Magical realism",
                "series_name": "Example series",
                "series_volume": "1",
            },
        )
        assert first.status_code == 201
        assert first.json()["isbn_10"] == "0306406152"
        assert first.json()["isbn_13"] == "9780306406157"

        duplicate = client.post(
            "/books",
            json={
                "title": "ISBN edition two",
                "author": "Identifier Author",
                "isbn_13": "9780306406157",
            },
        )
        assert duplicate.status_code == 201

        simple_search = client.get("/books", params={"search": "9780306406157"})
        assert simple_search.status_code == 200
        assert simple_search.json() == []

        found = client.get("/books", params={"isbn": "9780306406157"})
        assert found.status_code == 200
        assert {book["id"] for book in found.json()} == {
            first.json()["id"],
            duplicate.json()["id"],
        }

        cleared = client.patch(
            f'/books/{first.json()["id"]}',
            json={"isbn_10": "", "isbn_13": None},
        )
        assert cleared.status_code == 200
        assert cleared.json()["isbn_10"] is None
        assert cleared.json()["isbn_13"] is None


def test_advanced_metadata_filters_combine_and_offer_existing_values() -> None:
    with TestClient(app) as client:
        books = [
            {
                "title": "Galician mystery",
                "author": "First Author",
                "isbn_13": "9780306406157",
                "language": "Galician",
                "publisher": "North Press",
                "page_count": 250,
                "current_ed_year": 2020,
                "original_publication_year": 2001,
                "fiction_category": "FICTION",
                "binding": "PAPERBACK",
                "publication_type": "CONVENTIONAL_BOOK",
                "genre_text": "Crime, Mystery, Noir",
                "series_name": "Coastal cases",
            },
            {
                "title": "Galician reference",
                "author": "Second Author",
                "language": "Galician",
                "publisher": "North Press",
                "page_count": 420,
                "current_ed_year": 2024,
                "original_publication_year": 1980,
                "fiction_category": "NON_FICTION",
                "binding": "HARDCOVER",
                "publication_type": "REFERENCE",
                "genre_text": "History, Reference",
            },
            {
                "title": "Spanish mystery",
                "author": "Third Author",
                "language": "Spanish",
                "publisher": "South Press",
                "page_count": 190,
                "current_ed_year": 2019,
                "fiction_category": "FICTION",
                "binding": "PAPERBACK",
                "publication_type": "CONVENTIONAL_BOOK",
                "genre_text": "Mystery",
            },
        ]
        for book in books:
            assert client.post("/books", json=book).status_code == 201

        def titles(params: list[tuple[str, str]]) -> set[str]:
            response = client.get("/books", params=params)
            assert response.status_code == 200
            return {book["title"] for book in response.json()}

        assert titles([
            ("language", "Galician"),
            ("binding", "PAPERBACK"),
            ("page_max", "300"),
        ]) == {"Galician mystery"}
        assert titles([
            ("language", "Galician"),
            ("language", "Spanish"),
            ("genre", "Mystery"),
        ]) == {"Galician mystery", "Spanish mystery"}
        assert titles([
            ("series_state", "YES"),
            ("series_name", "Coastal cases"),
        ]) == {"Galician mystery"}
        assert titles([
            ("publication_year_field", "original_publication_year"),
            ("publication_year_min", "1990"),
            ("publication_year_max", "2010"),
        ]) == {"Galician mystery"}
        assert titles([("isbn", "978-0-306-40615-7")]) == {"Galician mystery"}
        assert titles([("search", "Coastal cases")]) == {"Galician mystery"}
        assert titles([("search", "North Press")]) == set()

        options = client.get("/metadata-options")
        assert options.status_code == 200
        assert options.json()["languages"] == ["Galician", "Spanish"]
        assert options.json()["genres"] == [
            "Crime", "History", "Mystery", "Noir", "Reference"
        ]

        invalid_range = client.get(
            "/books", params={"page_min": 400, "page_max": 200}
        )
        assert invalid_range.status_code == 422


def test_book_isbn_fields_reject_invalid_or_wrong_length_values() -> None:
    with TestClient(app) as client:
        invalid = client.post(
            "/books",
            json={
                "title": "Invalid identifier",
                "author": "Identifier Author",
                "isbn_13": "9780306406158",
            },
        )
        wrong_field = client.post(
            "/books",
            json={
                "title": "Wrong identifier field",
                "author": "Identifier Author",
                "isbn_10": "9780306406157",
            },
        )

    assert invalid.status_code == 422
    assert "checksum is invalid" in invalid.text
    assert wrong_field.status_code == 422
    assert "ISBN-10 field" in wrong_field.text


def test_multiple_authors_are_ordered_searchable_and_transactional() -> None:
    with TestClient(app) as client:
        invalid_author = client.post(
            "/books",
            json={
                "title": "Invalid canonical author",
                "author": "Varios",
                "has_multiple_authors": True,
                "structured_authors": ["One Author", "Two Author"],
            },
        )
        too_few = client.post(
            "/books",
            json={
                "title": "Too few authors",
                "author": "Multiple authors",
                "has_multiple_authors": True,
                "structured_authors": ["Only Author"],
            },
        )
        duplicate = client.post(
            "/books",
            json={
                "title": "Duplicate authors",
                "author": "Multiple authors",
                "has_multiple_authors": True,
                "structured_authors": ["Ursula K. Le Guin", " ursula  k. le guin "],
            },
        )
        assert invalid_author.status_code == 422
        assert too_few.status_code == 422
        assert duplicate.status_code == 422
        assert client.get("/books").json() == []

        created = client.post(
            "/books",
            json={
                "title": "Shared work",
                "author": "Multiple authors",
                "has_multiple_authors": True,
                "structured_authors": [
                    "First Writer", "Second Writer", "Third Writer"
                ],
            },
        )
        assert created.status_code == 201
        book = created.json()
        assert book["author"] == "Multiple authors"
        assert book["has_multiple_authors"] is True
        assert book["structured_authors"] == [
            "First Writer", "Second Writer", "Third Writer"
        ]

        by_name = client.get("/books", params={"search": "Second Writer"})
        by_multiple = client.get("/books", params={"search": "Multiple"})
        advanced = client.get(
            "/books", params={"author_structure": "MULTIPLE"}
        )
        assert [item["id"] for item in by_name.json()] == [book["id"]]
        assert [item["id"] for item in by_multiple.json()] == [book["id"]]
        assert [item["id"] for item in advanced.json()] == [book["id"]]

        csv_response = client.get("/exports/books.csv")
        csv_rows = list(
            csv.DictReader(
                csv_response.content.decode("utf-8-sig").splitlines()
            )
        )
        assert csv_rows[0]["author"] == "Multiple authors"
        assert csv_rows[0]["has_multiple_authors"] == "true"
        assert csv_rows[0]["structured_authors"] == (
            "First Writer | Second Writer | Third Writer"
        )

        reordered = client.patch(
            f'/books/{book["id"]}',
            json={
                "has_multiple_authors": True,
                "author": "Multiple authors",
                "structured_authors": ["Third Writer", "First Writer"],
            },
        )
        assert reordered.status_code == 200
        assert reordered.json()["structured_authors"] == [
            "Third Writer", "First Writer"
        ]

        missing_single_name = client.patch(
            f'/books/{book["id"]}', json={"has_multiple_authors": False}
        )
        assert missing_single_name.status_code == 422
        unchanged = client.get("/books", params={"book_id": book["id"]}).json()[0]
        assert unchanged["has_multiple_authors"] is True
        assert unchanged["structured_authors"] == ["Third Writer", "First Writer"]

        converted = client.patch(
            f'/books/{book["id"]}',
            json={
                "has_multiple_authors": False,
                "author": "Third Writer",
                "structured_authors": [],
            },
        )
        assert converted.status_code == 200
        assert converted.json()["author"] == "Third Writer"
        assert converted.json()["has_multiple_authors"] is False
        assert converted.json()["structured_authors"] == []

        with closing(connect_database(TEST_DATABASE)) as connection:
            assert connection.execute(
                "SELECT COUNT(*) FROM book_authors WHERE book_id = ?",
                (book["id"],),
            ).fetchone()[0] == 0


def test_multiple_authors_supports_large_contributor_lists_up_to_250() -> None:
    authors_150 = [f"Contributor {index:03d}" for index in range(1, 151)]
    authors_251 = [f"Contributor {index:03d}" for index in range(1, 252)]
    with TestClient(app) as client:
        accepted = client.post(
            "/books",
            json={
                "title": "Large collaborative work",
                "author": "Multiple authors",
                "has_multiple_authors": True,
                "structured_authors": authors_150,
            },
        )
        rejected = client.post(
            "/books",
            json={
                "title": "Too many contributors",
                "author": "Multiple authors",
                "has_multiple_authors": True,
                "structured_authors": authors_251,
            },
        )

    assert accepted.status_code == 201
    assert accepted.json()["structured_authors"] == authors_150
    assert rejected.status_code == 422


def test_book_bibliographic_metadata_is_optional_editable_and_searchable() -> None:
    metadata = {
        "subtitle": "A complete metadata test",
        "page_count": 432,
        "publisher": "Example Press",
        "current_ed_year": 2024,
        "original_publication_year": 1987,
        "language": "English",
        "edition_number": 2,
        "fiction_category": "FICTION",
        "binding": "HARDCOVER",
        "publication_type": "COMIC_GRAPHIC_NOVEL",
        "genre_text": "Historical, Science fiction",
        "series_name": "Example Cycle",
        "series_volume": "0.5",
    }
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={
                "title": "Metadata book",
                "author": "Metadata Author",
                **metadata,
            },
        )
        assert created.status_code == 201
        for field, value in metadata.items():
            assert created.json()[field] == value

        found = client.get("/books", params={"search": "Example Cycle"})
        assert [book["id"] for book in found.json()] == [created.json()["id"]]

        cleared = client.patch(
            f'/books/{created.json()["id"]}',
            json={
                "subtitle": "",
                "fiction_category": None,
                "binding": None,
                "publication_type": None,
            },
        )
        assert cleared.status_code == 200
        assert cleared.json()["subtitle"] is None
        assert cleared.json()["fiction_category"] is None
        assert cleared.json()["binding"] is None
        assert cleared.json()["publication_type"] is None


def test_genres_are_normalized_deduplicated_and_sorted() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={
                "title": "Normalized genres",
                "author": "Genre Author",
                "genre_text": " Horror ; Fantasy\nscience fiction; fantasy ",
            },
        )
        assert created.status_code == 201
        assert created.json()["genre_text"] == "Fantasy, Horror, science fiction"

        updated = client.patch(
            f'/books/{created.json()["id"]}',
            json={"genre_text": "Young Adult; U.S. History. Overview"},
        )
        assert updated.status_code == 200
        assert updated.json()["genre_text"] == (
            "U.S. History. Overview, Young Adult"
        )

        cleared = client.patch(
            f'/books/{created.json()["id"]}', json={"genre_text": " ; \n "}
        )
        assert cleared.status_code == 200
        assert cleared.json()["genre_text"] is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("page_count", 0),
        ("current_ed_year", 999),
        ("current_ed_year", 10000),
        ("original_publication_year", 20),
        ("edition_number", 0),
        ("fiction_category", "POETRY"),
        ("binding", "LEATHER"),
        ("publication_type", "MAP"),
    ],
)
def test_book_bibliographic_metadata_rejects_invalid_values(
    field: str,
    value: object,
) -> None:
    with TestClient(app) as client:
        response = client.post(
            "/books",
            json={
                "title": "Invalid metadata",
                "author": "Metadata Author",
                field: value,
            },
        )
    assert response.status_code == 422


def test_isbn_lookup_endpoint_rejects_an_invalid_checksum() -> None:
    with TestClient(app) as client:
        response = client.get(
            "/bibliography/isbn", params={"isbn": "978-0-306-40615-8"}
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "ISBN-13 checksum is invalid"


def test_isbn_lookup_endpoint_reports_provider_outage() -> None:
    from app.bibliography import BibliographicProvidersUnavailable

    with patch(
        "app.main.lookup_isbn",
        side_effect=BibliographicProvidersUnavailable("both failed"),
    ):
        with TestClient(app) as client:
            response = client.get(
                "/bibliography/isbn", params={"isbn": "9780306406157"}
            )

    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Bibliographic lookup services are temporarily unavailable"
    )


def test_isbn_lookup_finds_local_equivalent_when_providers_are_unavailable() -> None:
    from app.bibliography import BibliographicProvidersUnavailable

    with TestClient(app) as client:
        existing = client.post(
            "/books",
            json={
                "title": "Locally identified book",
                "author": "Offline Author",
                "isbn_10": "0306406152",
            },
        ).json()
        with patch(
            "app.main.lookup_isbn",
            side_effect=BibliographicProvidersUnavailable("both failed"),
        ):
            response = client.get(
                "/bibliography/isbn", params={"isbn": "9780306406157"}
            )

    assert response.status_code == 200
    assert response.json()["candidates"] == []
    assert response.json()["catalogue_matches"] == [
        {
            "book_id": existing["id"],
            "title": "Locally identified book",
            "author": "Offline Author",
            "status": "PENDING",
            "cover_filename": None,
            "location_label": None,
            "match_class": "strong",
            "reason": "Exact ISBN already stored in BOOKPILE",
        }
    ]


def test_isbn_lookup_endpoint_returns_existing_catalogue_matches() -> None:
    candidate = {
        "source": "OPEN_LIBRARY",
        "source_record_id": "OL2M",
        "identifiers": {"isbn_10": None, "isbn_13": "9780306406157"},
        "title": "Cien anos de soledad",
        "subtitle": None,
        "authors": ["Gabriel García Márquez"],
        "publisher": None,
        "published_date": None,
        "page_count": None,
        "subjects": [],
        "language": None,
        "edition": None,
        "genres": [],
        "category": None,
        "format": None,
        "confidence_or_match_notes": None,
    }
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={
                "title": "Cien años de soledad",
                "author": "Gabriel Garcia Marquez",
                "isbn_10": "0306406152",
            },
        ).json()
        with patch("app.main.lookup_isbn", return_value=[candidate]):
            response = client.get(
                "/bibliography/isbn", params={"isbn": "9780306406157"}
            )

    matches = response.json()["candidates"][0]["catalogue_matches"]
    assert matches == [
        {
            "book_id": created["id"],
            "title": "Cien años de soledad",
            "author": "Gabriel Garcia Marquez",
            "status": "PENDING",
            "cover_filename": None,
            "location_label": None,
            "match_class": "strong",
            "reason": "Exact ISBN already stored in BOOKPILE",
        }
    ]


def test_bibliographic_text_match_endpoint_is_read_only() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={"title": "The Dispossessed", "author": "Ursula K. Le Guin"},
        ).json()
        before = client.get("/stats").json()
        response = client.post(
            "/bibliography/matches",
            json={"title": "The Dispossessed", "authors": ["Ursula Le Guin"]},
        )
        after = client.get("/stats").json()

    assert response.status_code == 200
    assert response.json()[0]["book_id"] == created["id"]
    assert response.json()[0]["match_class"] == "strong"
    assert before == after


def create_rearrangement_fixture(client: TestClient) -> tuple[dict, dict, list[dict]]:
    bookcase = client.post("/bookcases", json={"name": "Move room"}).json()
    shelf = client.post(
        "/shelves",
        json={"bookcase_id": bookcase["id"], "shelf_number": 1},
    ).json()
    first_container = client.post(
        "/containers",
        json={
            "shelf_id": shelf["id"],
            "container_type": "ROW",
            "layer": "BACKGROUND",
            "container_number": 1,
        },
    ).json()
    second_container = client.post(
        "/containers",
        json={
            "shelf_id": shelf["id"],
            "container_type": "ROW",
            "layer": "BACKGROUND",
            "container_number": 2,
        },
    ).json()
    books = [
        client.post(
            "/books",
            json={
                "title": f"Move {position}",
                "author": "Mover",
                "container_id": first_container["id"],
                "position": position,
            },
        ).json()
        for position in range(1, 5)
    ]
    return first_container, second_container, books


def test_rearrangement_preview_is_read_only_and_squeeze_stops_at_gap() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        payload = {
            "book_id": books[3]["id"],
            "old_position_mode": "LEAVE_GAP",
            "steps": [
                {
                    "container_id": first["id"],
                    "position": 2,
                    "new_position_mode": "SQUEEZE",
                }
            ],
        }
        preview = client.post("/rearrangements/preview", json=payload)
        unchanged = client.get(
            "/books", params={"container_id": first["id"], "sort_by": "physical"}
        ).json()

    assert preview.status_code == 200
    assert preview.json()["valid_to_apply"] is True
    placements = {
        item["book_id"]: item["position"]
        for item in preview.json()["placements"]
    }
    assert placements == {
        books[1]["id"]: 3,
        books[2]["id"]: 4,
        books[3]["id"]: 2,
    }
    assert [(book["id"], book["position"]) for book in unchanged] == [
        (book["id"], index) for index, book in enumerate(books, 1)
    ]


def test_rearrangement_swap_overrides_collapse() -> None:
    with TestClient(app) as client:
        first, second, books = create_rearrangement_fixture(client)
        target = client.post(
            "/books",
            json={
                "title": "Swap target",
                "author": "Mover",
                "container_id": second["id"],
                "position": 1,
            },
        ).json()
        preview = client.post(
            "/rearrangements/preview",
            json={
                "book_id": books[0]["id"],
                "old_position_mode": "COLLAPSE",
                "steps": [
                    {
                        "container_id": second["id"],
                        "position": 1,
                        "new_position_mode": "SWAP",
                    }
                ],
            },
        ).json()

    placements = {
        item["book_id"]: (item["container_id"], item["position"])
        for item in preview["placements"]
    }
    assert preview["effective_old_position_mode"] == "LEAVE_GAP"
    assert placements[books[0]["id"]] == (second["id"], 1)
    assert placements[target["id"]] == (first["id"], 1)
    assert books[1]["id"] not in placements


def test_rearrangement_continue_chain_is_provisional_and_atomic() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        payload = {
            "book_id": books[0]["id"],
            "old_position_mode": "LEAVE_GAP",
            "steps": [
                {
                    "container_id": first["id"],
                    "position": 2,
                    "new_position_mode": "CONTINUE",
                },
                {
                    "container_id": first["id"],
                    "position": 3,
                    "new_position_mode": "CONTINUE",
                },
                {
                    "container_id": first["id"],
                    "position": 1,
                    "new_position_mode": "CONTINUE",
                },
            ],
        }
        preview = client.post("/rearrangements/preview", json=payload).json()
        applied = client.post(
            "/rearrangements/apply",
            json={**payload, "revision": preview["revision"]},
        )
        ordered = client.get(
            "/books", params={"container_id": first["id"], "sort_by": "physical"}
        ).json()

    assert preview["complete"] is True
    assert preview["valid_to_apply"] is True
    assert preview["gaps"] == []
    assert applied.status_code == 200
    assert [book["title"] for book in ordered] == [
        "Move 3",
        "Move 1",
        "Move 2",
        "Move 4",
    ]


def test_incomplete_or_gapped_rearrangement_cannot_be_applied() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        payload = {
            "book_id": books[0]["id"],
            "old_position_mode": "LEAVE_GAP",
            "steps": [
                {
                    "container_id": first["id"],
                    "position": 2,
                    "new_position_mode": "CONTINUE",
                }
            ],
        }
        preview = client.post("/rearrangements/preview", json=payload).json()
        applied = client.post(
            "/rearrangements/apply",
            json={**payload, "revision": preview["revision"]},
        )

    assert preview["complete"] is False
    assert preview["next_active_book_id"] == books[1]["id"]
    assert preview["valid_to_apply"] is False
    assert applied.status_code == 409


def test_reading_area_rearrangements_preserve_or_confirm_physical_position() -> None:
    with TestClient(app) as client:
        first, second, books = create_rearrangement_fixture(client)
        to_reading_payload = {
            "book_id": books[0]["id"],
            "steps": [{"destination_kind": "READING"}],
        }
        reading_preview = client.post(
            "/rearrangements/preview", json=to_reading_payload
        ).json()
        client.post(
            "/rearrangements/apply",
            json={**to_reading_payload, "revision": reading_preview["revision"]},
        )
        reading_book = client.get(
            "/books", params={"book_id": books[0]["id"]}
        ).json()[0]

        return_payload = {
            "book_id": books[0]["id"],
            "old_position_mode": "COLLAPSE",
            "steps": [
                {
                    "container_id": second["id"],
                    "position": 1,
                    "new_position_mode": "SQUEEZE",
                    "reading_exit_status": "READ",
                }
            ],
        }
        return_preview = client.post(
            "/rearrangements/preview", json=return_payload
        ).json()
        returned = client.post(
            "/rearrangements/apply",
            json={**return_payload, "revision": return_preview["revision"]},
        )
        returned_book = client.get(
            "/books", params={"book_id": books[0]["id"]}
        ).json()[0]

    assert reading_book["status"] == "CURRENTLY_READING"
    assert reading_book["container_id"] == first["id"]
    assert reading_book["position"] == 1
    assert returned.status_code == 200
    assert returned_book["status"] == "READ"
    assert returned_book["container_id"] == second["id"]
    assert returned_book["position"] == 1


def test_completed_rearrangement_with_a_gap_cannot_be_applied() -> None:
    with TestClient(app) as client:
        first, second, books = create_rearrangement_fixture(client)
        payload = {
            "book_id": books[1]["id"],
            "old_position_mode": "LEAVE_GAP",
            "steps": [
                {
                    "container_id": second["id"],
                    "position": 1,
                    "new_position_mode": "SQUEEZE",
                }
            ],
        }
        preview = client.post("/rearrangements/preview", json=payload).json()
        applied = client.post(
            "/rearrangements/apply",
            json={**payload, "revision": preview["revision"]},
        )

    assert preview["complete"] is True
    assert preview["gaps"] == [{"container_id": first["id"], "positions": [2]}]
    assert preview["valid_to_apply"] is False
    assert applied.status_code == 409


def test_rearrangement_rejects_positions_beyond_next_end() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        response = client.post(
            "/rearrangements/preview",
            json={
                "book_id": books[0]["id"],
                "steps": [{"container_id": first["id"], "position": 8}],
            },
        )

    assert response.status_code == 422
    assert "next end position" in response.json()["detail"]


def test_rearrangement_apply_rejects_a_stale_preview() -> None:
    with TestClient(app) as client:
        first, second, books = create_rearrangement_fixture(client)
        payload = {
            "book_id": books[0]["id"],
            "steps": [{"container_id": second["id"], "position": 1}],
        }
        preview = client.post("/rearrangements/preview", json=payload).json()
        changed = {**books[2], "status": "READ", "reading_started_date": "2026-08-06", "read_date": "2026-08-06"}
        assert client.patch(f'/books/{books[2]["id"]}', json=changed).status_code == 200
        applied = client.post(
            "/rearrangements/apply",
            json={**payload, "revision": preview["revision"]},
        )

    assert applied.status_code == 409
    assert "changed" in applied.json()["detail"]


def test_reading_book_can_return_to_its_retained_position_as_status_only() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        reading = {**books[1], "status": "CURRENTLY_READING"}
        assert client.patch(f'/books/{books[1]["id"]}', json=reading).status_code == 200
        payload = {
            "book_id": books[1]["id"],
            "steps": [
                {
                    "container_id": first["id"],
                    "position": 2,
                    "reading_exit_status": "PENDING",
                }
            ],
        }
        preview = client.post("/rearrangements/preview", json=payload).json()
        applied = client.post(
            "/rearrangements/apply",
            json={**payload, "revision": preview["revision"]},
        )
        returned = client.get(
            "/books", params={"book_id": books[1]["id"]}
        ).json()[0]

    assert preview["valid_to_apply"] is True
    assert applied.status_code == 200
    assert returned["status"] == "PENDING"
    assert returned["container_id"] == first["id"]
    assert returned["position"] == 2


def test_read_book_can_move_to_rereading_with_history_preserved() -> None:
    with TestClient(app) as client:
        _, _, books = create_rearrangement_fixture(client)
        read = {**books[0], "status": "READ", "reading_started_date": "2026-08-06", "read_date": "2026-08-06"}
        assert client.patch(f'/books/{books[0]["id"]}', json=read).status_code == 200
        preview = client.post(
            "/rearrangements/preview",
            json={
                "book_id": books[0]["id"],
                "steps": [{"destination_kind": "READING"}],
            },
        )
        assert preview.status_code == 200
        result = client.post(
            "/rearrangements/apply",
            json={
                "book_id": books[0]["id"],
                "steps": [{"destination_kind": "READING"}],
                "revision": preview.json()["revision"],
            },
        )
        updated = client.get(
            "/books", params={"book_id": books[0]["id"]}
        ).json()[0]
        stats = client.get("/stats").json()

    assert result.status_code == 200
    assert updated["status"] == "CURRENTLY_READING"
    assert updated["is_rereading"] is True
    assert updated["reading_session_count"] == 2
    assert updated["reading_sessions"][0]["finished_date"] == "2026-08-06"
    assert stats["currently_reading"] == 0
    assert stats["currently_rereading"] == 1
    assert stats["read"] == 1


def test_rearrangement_summarizes_automatic_shifts() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        collapse_preview = client.post(
            "/rearrangements/preview",
            json={
                "book_id": books[0]["id"],
                "steps": [{"container_id": first["id"], "position": 3}],
            },
        ).json()
        squeeze_preview = client.post(
            "/rearrangements/preview",
            json={
                "book_id": books[3]["id"],
                "steps": [{"container_id": first["id"], "position": 1}],
            },
        ).json()

    assert collapse_preview["movement_log"][1] == (
        "2 books shifted to fill the gap and make new room."
    )
    assert squeeze_preview["movement_log"][1] == (
        "3 books shifted to fill the gap and make new room."
    )
    assert all("Move 2" not in line for line in collapse_preview["movement_log"])


def test_multiple_completed_movement_chains_share_one_preview_and_apply() -> None:
    with TestClient(app) as client:
        first, _, books = create_rearrangement_fixture(client)
        first_operation = {
            "book_id": books[0]["id"],
            "old_position_mode": "COLLAPSE",
            "steps": [
                {
                    "container_id": first["id"],
                    "position": 4,
                    "new_position_mode": "SQUEEZE",
                }
            ],
        }
        payload = {
            "completed_operations": [first_operation],
            "book_id": books[1]["id"],
            "old_position_mode": "COLLAPSE",
            "steps": [
                {
                    "container_id": first["id"],
                    "position": 4,
                    "new_position_mode": "SQUEEZE",
                }
            ],
        }
        preview = client.post("/rearrangements/preview", json=payload).json()
        before = client.get(
            "/books", params={"container_id": first["id"], "sort_by": "physical"}
        ).json()
        applied = client.post(
            "/rearrangements/apply",
            json={**payload, "revision": preview["revision"]},
        )
        after = client.get(
            "/books", params={"container_id": first["id"], "sort_by": "physical"}
        ).json()

    assert preview["valid_to_apply"] is True
    assert len(preview["movement_groups"]) == 2
    assert preview["movement_groups"][0][0].startswith('“Move 1”')
    assert preview["movement_groups"][1][0].startswith('“Move 2”')
    assert [book["title"] for book in before] == [
        "Move 1", "Move 2", "Move 3", "Move 4"
    ]
    assert applied.status_code == 200
    assert [book["title"] for book in after] == [
        "Move 3", "Move 4", "Move 1", "Move 2"
    ]


def test_read_only_statistics_use_known_dates_and_report_exclusions() -> None:
    with TestClient(app) as client:
        books = [
            {
                "title": "Original read",
                "author": "Author",
                "status": "READ",
                "is_original_collection": True,
                "reading_started_date": "2024-01-05",
                "read_date": "2024-01-05",
            },
            {
                "title": "Later read",
                "author": "Author",
                "status": "READ",
                "acquisition_date": "2023-12-01",
                "reading_started_date": "2024-01-10",
                "read_date": "2024-01-14",
            },
            {
                "title": "Reading now",
                "author": "Author",
                "status": "CURRENTLY_READING",
                "acquisition_date": "2024-02-01",
                "reading_started_date": "2024-02-03",
            },
            {
                "title": "Pending",
                "author": "Author",
                "acquisition_date": "2024-03-01",
            },
        ]
        for book in books:
            assert client.post("/books", json=book).status_code == 201

        response = client.get("/statistics", params={"year": 2024})

        assert response.status_code == 200
        result = response.json()
        assert result["available_years"] == [2023, 2024]
        assert result["monthly"][0] == {
            "month": 1,
            "acquired": 0,
            "read": 2,
            "pages_read": 0.0,
        }
        assert result["monthly"][1] == {
            "month": 2,
            "acquired": 1,
            "read": 0,
            "pages_read": 0.0,
        }
        assert result["pending_duration"] == {
            "average_days": 22.0,
            "median_days": 22.0,
            "sample_size": 2,
            "excluded": 1,
        }
        assert result["reading_duration"] == {
            "average_days": 3.0,
            "median_days": 3.0,
            "sample_size": 2,
            "excluded": 0,
        }
        assert result["original_collection"] == {
            "total": 1,
            "pending": 0,
            "reading": 0,
            "read": 1,
        }
        assert result["later_acquisitions"] == {
            "total": 3,
            "pending": 1,
            "reading": 1,
            "read": 1,
        }
        empty_period = client.get(
            "/statistics", params={"year": 2022}
        ).json()
        assert all(
            item["acquired"] == 0 and item["read"] == 0
            for item in empty_period["monthly"]
        )


def test_statistics_filter_metadata_and_distribute_pages_over_reading_days() -> None:
    with TestClient(app) as client:
        books = [
            {
                "title": "Five day Galician book",
                "author": "Author",
                "status": "READ",
                "language": "Galician",
                "binding": "PAPERBACK",
                "page_count": 500,
                "reading_started_date": "2024-01-10",
                "read_date": "2024-01-14",
            },
            {
                "title": "One day Galician book",
                "author": "Author",
                "status": "READ",
                "language": "Galician",
                "binding": "HARDCOVER",
                "page_count": 120,
                "reading_started_date": "2024-02-02",
                "read_date": "2024-02-02",
            },
            {
                "title": "Spanish book",
                "author": "Author",
                "status": "READ",
                "language": "Spanish",
                "binding": "PAPERBACK",
                "page_count": 300,
                "reading_started_date": "2024-03-01",
                "read_date": "2024-03-03",
            },
            {
                "title": "Missing pages",
                "author": "Author",
                "status": "READ",
                "language": "Galician",
                "binding": "PAPERBACK",
                "reading_started_date": "2024-04-01",
                "read_date": "2024-04-01",
            },
        ]
        for book in books:
            assert client.post("/books", json=book).status_code == 201

        response = client.get(
            "/statistics",
            params=[
                ("year", "2024"),
                ("language", "Galician"),
                ("binding", "PAPERBACK"),
            ],
        )
        assert response.status_code == 200
        result = response.json()
        assert result["filtered_book_count"] == 2
        assert sum(item["read"] for item in result["monthly"]) == 2
        assert result["monthly"][0]["pages_read"] == 500.0
        assert result["reading_rate"]["total_pages"] == 500.0
        assert result["reading_rate"]["sample_size"] == 1
        assert result["reading_rate"]["excluded"] == 1
        assert result["reading_rate"]["single_day_estimates"] == 0
        assert result["reading_rate"]["average_per_book"] == 100.0
        assert result["reading_rate"]["median_per_book"] == 100.0
        assert result["reading_rate"]["per_book_sample_size"] == 1
        assert result["reading_rate"]["per_book_excluded"] == 1
        assert result["reading_rate"]["per_book"] == [
            {
                    "id": result["reading_rate"]["per_book"][0]["id"],
                    "session_number": 1,
                "title": "Five day Galician book",
                "author": "Author",
                "page_count": 500,
                "reading_days": 5,
                "pages_per_day": 100.0,
                "read_date": "2024-01-14",
                "estimated_start": False,
            }
        ]

        galician = client.get(
            "/statistics", params=[("year", "2024"), ("language", "Galician")]
        ).json()
        assert galician["filtered_book_count"] == 3
        assert galician["reading_rate"]["total_pages"] == 620.0
        assert galician["reading_rate"]["single_day_estimates"] == 0
        assert galician["reading_rate"]["average_per_book"] == 110.0
        assert galician["reading_rate"]["median_per_book"] == 110.0
        assert galician["reading_rate"]["per_book_estimates"] == 0


def test_reading_suggestions_support_modes_thresholds_and_exclusions() -> None:
    with TestClient(app) as client:
        for title, acquired in (
            ("Oldest pending", "2000-01-01"),
            ("Newer pending", "2025-01-01"),
            ("Unknown acquisition", None),
        ):
            response = client.post(
                "/books",
                json={
                    "title": title,
                    "author": "Author",
                    "acquisition_date": acquired,
                    "is_original_collection": acquired is None,
                },
            )
            assert response.status_code == 201

        oldest = client.get("/suggestions", params={"mode": "oldest"})
        assert oldest.status_code == 200
        assert oldest.json()["book"]["title"] == "Oldest pending"
        assert oldest.json()["waiting_days"] > 365

        next_oldest = client.get(
            "/suggestions",
            params=[
                ("mode", "oldest"),
                ("exclude_id", oldest.json()["book"]["id"]),
            ],
        )
        assert next_oldest.json()["book"]["title"] == "Newer pending"

        long_wait = client.get(
            "/suggestions",
            params={"mode": "waiting", "minimum_days": 5000},
        )
        assert long_wait.status_code == 200
        assert long_wait.json()["book"]["title"] == "Oldest pending"

        random_suggestion = client.get(
            "/suggestions", params={"mode": "random"}
        )
        assert random_suggestion.status_code == 200
        assert random_suggestion.json()["book"]["title"] in {
            "Oldest pending",
            "Newer pending",
            "Unknown acquisition",
        }


def test_reading_suggestions_apply_combined_metadata_filters() -> None:
    with TestClient(app) as client:
        for title, language, binding, pages in (
            ("Short Galician paperback", "Galician", "PAPERBACK", 180),
            ("Long Galician hardcover", "Galician", "HARDCOVER", 520),
            ("Short English paperback", "English", "PAPERBACK", 160),
        ):
            response = client.post(
                "/books",
                json={
                    "title": title,
                    "author": "Suggestion Author",
                    "language": language,
                    "binding": binding,
                    "page_count": pages,
                },
            )
            assert response.status_code == 201

        filtered = client.get(
            "/suggestions",
            params=[
                ("mode", "random"),
                ("language", "Galician"),
                ("binding", "PAPERBACK"),
                ("page_max", "300"),
            ],
        )
        impossible = client.get(
            "/suggestions",
            params=[("language", "Galician"), ("page_max", "100")],
        )

    assert filtered.status_code == 200
    assert filtered.json()["book"]["title"] == "Short Galician paperback"
    assert impossible.status_code == 404


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


def test_library_hierarchy_can_be_edited_without_losing_assignments() -> None:
    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases",
            json={"name": "Office", "description": "Old description"},
        ).json()
        shelf_one = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 1},
        ).json()
        shelf_two = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 2},
        ).json()
        container_one = client.post(
            "/containers",
            json={
                "shelf_id": shelf_one["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        ).json()
        container_two = client.post(
            "/containers",
            json={
                "shelf_id": shelf_one["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 2,
            },
        ).json()
        book = client.post(
            "/books",
            json={
                "title": "The Dispossessed",
                "author": "Ursula K. Le Guin",
                "container_id": container_one["id"],
                "position": 1,
            },
        ).json()

        renamed = client.patch(
            f'/bookcases/{bookcase["id"]}',
            json={"name": "Study", "description": "West wall"},
        )
        swapped_shelves = client.patch(
            f'/shelves/{shelf_one["id"]}', json={"shelf_number": 2}
        )
        swapped_containers = client.patch(
            f'/containers/{container_one["id"]}',
            json={"container_number": 2},
        )

        assert renamed.status_code == 200
        assert renamed.json()["name"] == "Study"
        assert renamed.json()["description"] == "West wall"
        assert swapped_shelves.status_code == 200
        assert swapped_containers.status_code == 200

        library = client.get("/library").json()[0]
        shelves = {item["id"]: item for item in library["shelves"]}
        assert shelves[shelf_one["id"]]["shelf_number"] == 2
        assert shelves[shelf_two["id"]]["shelf_number"] == 1
        containers = {
            item["id"]: item
            for item in shelves[shelf_one["id"]]["containers"]
        }
        assert containers[container_one["id"]]["container_number"] == 2
        assert containers[container_two["id"]]["container_number"] == 1

        assigned = client.get(
            "/books", params={"book_id": book["id"]}
        ).json()[0]
        assert assigned["container_id"] == container_one["id"]
        assert assigned["position"] == 1
        assert assigned["location_label"] == (
            "Study · Shelf 2 · Background Row 2 · Position 1"
        )


def test_currently_reading_book_preserves_library_position() -> None:
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
        assert reading.json()["container_id"] == container.json()["id"]
        assert reading.json()["position"] == 1
        assert reading.json()["reading_started_date"] == date.today().isoformat()
        assert client.get("/stats").json()["currently_reading"] == 1


def test_assigning_reading_book_to_occupied_position_shifts_container() -> None:
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
                "container_type": "PILE",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        )
        reading = client.post(
            "/books",
            json={
                "title": "Reading now",
                "author": "Author",
                "status": "CURRENTLY_READING",
            },
        ).json()
        existing = []
        for position in (1, 2, 3):
            existing.append(
                client.post(
                    "/books",
                    json={
                        "title": f"Existing {position}",
                        "author": "Author",
                        "container_id": container.json()["id"],
                        "position": position,
                    },
                ).json()
            )

        assigned = client.patch(
            f'/books/{reading["id"]}',
            json={
                "status": "READ",
                "container_id": container.json()["id"],
                "position": 1,
                    "read_date": reading["reading_started_date"],
                    "is_read_date_unknown": False,
            },
        )

        assert assigned.status_code == 200
        books = {
            book["title"]: book
            for book in client.get(
                "/books",
                params={"container_id": container.json()["id"], "sort_by": "physical"},
            ).json()
        }
        assert books["Reading now"]["position"] == 1
        assert books["Existing 1"]["position"] == 2
        assert books["Existing 2"]["position"] == 3
        assert books["Existing 3"]["position"] == 4


def test_setting_book_to_reading_preserves_container_sequence() -> None:
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
        books = []
        for position in (1, 2, 3):
            books.append(
                client.post(
                    "/books",
                    json={
                        "title": f"Book {position}",
                        "author": "Author",
                        "container_id": container.json()["id"],
                        "position": position,
                    },
                ).json()
            )

        reading = client.patch(
            f'/books/{books[1]["id"]}',
            json={"status": "CURRENTLY_READING"},
        )

        assert reading.status_code == 200
        assert reading.json()["container_id"] == container.json()["id"]
        assert reading.json()["position"] == 2
        positions = {
            book["title"]: book["position"]
            for book in client.get(
                "/books",
                params={"container_id": container.json()["id"], "sort_by": "physical"},
            ).json()
        }
        assert positions == {"Book 1": 1, "Book 2": 2, "Book 3": 3}


def test_deleting_book_closes_position_gap() -> None:
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
        books = []
        for position in (1, 2, 3):
            books.append(
                client.post(
                    "/books",
                    json={
                        "title": f"Book {position}",
                        "author": "Author",
                        "container_id": container.json()["id"],
                        "position": position,
                    },
                ).json()
            )

        deleted = client.delete(f'/books/{books[0]["id"]}')

        assert deleted.status_code == 204
        positions = {
            book["title"]: book["position"]
            for book in client.get(
                "/books",
                params={"container_id": container.json()["id"], "sort_by": "physical"},
            ).json()
        }
        assert positions == {"Book 2": 1, "Book 3": 2}


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
        assert read.json()["read_date"] is None
        assert read.json()["is_read_date_unknown"] is True

        corrected = client.patch(
            f'/books/{created.json()["id"]}',
            json={
                "reading_started_date": "2026-06-10",
                "read_date": "2026-06-20",
            },
        )
        assert corrected.status_code == 200, corrected.text
        assert corrected.json()["reading_started_date"] == "2026-06-10"
        assert corrected.json()["read_date"] == "2026-06-20"


def test_read_book_can_have_an_explicitly_unknown_reading_date() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={
                "title": "An old favourite",
                "author": "Remembered Author",
                "status": "READ",
                "is_read_date_unknown": True,
            },
        )
        assert created.status_code == 201
        assert created.json()["status"] == "READ"
        assert created.json()["read_date"] is None
        assert created.json()["is_read_date_unknown"] is True

        dated = client.patch(
            f'/books/{created.json()["id"]}',
            json={
                "reading_started_date": "2001-05-12",
                "read_date": "2001-05-12",
                "is_read_date_unknown": False,
            },
        )
        assert dated.status_code == 200
        assert dated.json()["read_date"] == "2001-05-12"
        assert dated.json()["is_read_date_unknown"] is False

        unknown_again = client.patch(
            f'/books/{created.json()["id"]}',
            json={"is_read_date_unknown": True},
        )
        assert unknown_again.status_code == 200
        assert unknown_again.json()["read_date"] is None
        assert unknown_again.json()["is_read_date_unknown"] is True

        pending = client.patch(
            f'/books/{created.json()["id"]}',
            json={"status": "PENDING"},
        )
        assert pending.status_code == 200
        assert pending.json()["is_read_date_unknown"] is False


def test_original_collection_clears_acquisition_date() -> None:
    with TestClient(app) as client:
        created = client.post(
            "/books",
            json={
                "title": "Inherited shelf book",
                "author": "Old Author",
                "acquisition_date": "2010-03-04",
            },
        ).json()
        assert created["acquisition_date"] == "2010-03-04"

        original = client.patch(
            f'/books/{created["id"]}',
            json={"is_original_collection": True},
        )
        assert original.status_code == 200
        assert original.json()["is_original_collection"] is True
        assert original.json()["acquisition_date"] is None

        newly_dated = client.patch(
            f'/books/{created["id"]}',
            json={"acquisition_date": "2012-07-08"},
        )
        assert newly_dated.status_code == 200
        assert newly_dated.json()["acquisition_date"] == "2012-07-08"
        assert newly_dated.json()["is_original_collection"] is False

        created_original = client.post(
            "/books",
            json={
                "title": "Another inherited book",
                "author": "Old Author",
                "acquisition_date": "1999-01-01",
                "is_original_collection": True,
            },
        )
        assert created_original.status_code == 201
        assert created_original.json()["acquisition_date"] is None


def test_book_dates_must_follow_chronological_order() -> None:
    with TestClient(app) as client:
        invalid_started = client.post(
            "/books",
            json={
                "title": "Time traveller one",
                "author": "Chronology",
                "acquisition_date": "2020-05-10",
                "reading_started_date": "2020-05-09",
            },
        )
        assert invalid_started.status_code == 422
        assert "earlier than acquisition" in invalid_started.json()["detail"]

        invalid_finished = client.post(
            "/books",
            json={
                "title": "Time traveller two",
                "author": "Chronology",
                "status": "READ",
                "reading_started_date": "2020-05-10",
                "read_date": "2020-05-09",
            },
        )
        assert invalid_finished.status_code == 422
        assert "earlier than reading started" in invalid_finished.json()["detail"]

        book = client.post(
            "/books",
            json={
                "title": "Ordered history",
                "author": "Chronology",
                "status": "READ",
                "acquisition_date": "2020-05-01",
                "reading_started_date": "2020-05-05",
                "read_date": "2020-05-10",
            },
        ).json()
        invalid_update = client.patch(
            f'/books/{book["id"]}',
            json={"acquisition_date": "2020-05-06"},
        )
        assert invalid_update.status_code == 422
        assert "earlier than acquisition" in invalid_update.json()["detail"]


def test_future_reading_dates_are_rejected() -> None:
    with TestClient(app) as client:
        future_acquisition = "2099-01-02"
        created = client.post(
            "/books",
            json={
                "title": "Future acquisition",
                "author": "Chronology",
                "status": "READ",
                "acquisition_date": future_acquisition,
                "reading_started_date": future_acquisition,
                "read_date": future_acquisition,
            },
        )
        assert created.status_code == 422

        started = client.post(
            "/books",
            json={
                "title": "Future reading",
                "author": "Chronology",
                "status": "CURRENTLY_READING",
                "acquisition_date": future_acquisition,
            },
        )
        assert started.status_code == 422


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
        assert row["is_read_date_unknown"] == 0
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
                "isbn_10": "0-306-40615-2",
                "isbn_13": "978-0-306-40615-7",
                "subtitle": "A metadata export",
                "page_count": 320,
                "publisher": "Example Press",
                "current_ed_year": 2024,
                "original_publication_year": 1967,
                "language": "Spanish",
                "edition_number": 2,
                "fiction_category": "FICTION",
                "binding": "PAPERBACK",
                "publication_type": "CONVENTIONAL_BOOK",
                "genre_text": "Magical realism",
                "series_name": "Example series",
                "series_volume": "1",
                "status": "READ",
                "reading_started_date": "2026-06-20",
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
    assert rows[0]["has_multiple_authors"] == "false"
    assert rows[0]["structured_authors"] == ""
    assert rows[0]["isbn_10"] == "0306406152"
    assert rows[0]["isbn_13"] == "9780306406157"
    assert rows[0]["subtitle"] == "A metadata export"
    assert rows[0]["page_count"] == "320"
    assert rows[0]["publisher"] == "Example Press"
    assert rows[0]["current_ed_year"] == "2024"
    assert rows[0]["original_publication_year"] == "1967"
    assert rows[0]["language"] == "Spanish"
    assert rows[0]["edition_number"] == "2"
    assert rows[0]["fiction_category"] == "FICTION"
    assert rows[0]["binding"] == "PAPERBACK"
    assert rows[0]["publication_type"] == "CONVENTIONAL_BOOK"
    assert rows[0]["genre_text"] == "Magical realism"
    assert rows[0]["series_name"] == "Example series"
    assert rows[0]["series_volume"] == "1"
    assert rows[0]["read_date"] == "2026-06-20"
    assert rows[0]["is_read_date_unknown"] == "false"
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

        with closing(connect_database(TEST_DATABASE)) as connection:
            assert schema_version(connection) == 5

    backup_directory = TEST_DATABASE.parent.parent / "backups"
    for pattern in ("pre-restore-*.zip", "BOOKPILE-pre-migration-*.zip"):
        for backup_file in backup_directory.glob(pattern):
            backup_file.unlink(missing_ok=True)


def test_restore_keeps_live_catalogue_if_incoming_migration_fails() -> None:
    with TestClient(app) as client:
        client.post(
            "/books",
            json={"title": "Archived book", "author": "Author One"},
        )
        backup = client.get("/exports/full-backup")
        client.post(
            "/books",
            json={"title": "Live-only book", "author": "Author Two"},
        )

        inspection = client.post(
            "/restore/inspect",
            files={"backup": ("saved.zip", backup.content, "application/zip")},
        )
        assert inspection.status_code == 200

        with patch(
            "app.restore.run_migrations",
            side_effect=ValueError("simulated incoming migration failure"),
        ):
            restored = client.post(f'/restore/{inspection.json()["token"]}')

        assert restored.status_code == 409
        assert "simulated incoming migration failure" in restored.json()["detail"]
        assert {book["title"] for book in client.get("/books").json()} == {
            "Archived book",
            "Live-only book",
        }

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
        created_books = []
        for book in books:
            created = client.post("/books", json=book)
            assert created.status_code == 201
            created_books.append(created.json())

        exact_book = client.get(
            "/books",
            params={"book_id": created_books[1]["id"]},
        ).json()
        assert [book["title"] for book in exact_book] == ["Alpha"]

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
        ]
        read_desc_with_unknown = client.get(
            "/books",
            params={
                "sort_by": "read_date",
                "sort_order": "desc",
                "include_unknown_sort_dates": True,
            },
        ).json()
        assert [book["title"] for book in read_desc_with_unknown] == [
            "Zulu",
            "Alpha",
            "Middle",
        ]

        invalid_dates = client.get(
            "/books",
            params={"date_from": "2026-01-01", "date_to": "2025-01-01"},
        )
        assert invalid_dates.status_code == 422


def test_books_can_be_filtered_by_missing_data_and_unknown_dates() -> None:
    image_bytes = BytesIO()
    Image.new("RGB", (120, 180), "#54756d").save(image_bytes, "JPEG")

    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases", json={"name": "Data Quality"}
        ).json()
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

        pending_complete = client.post(
            "/books",
            json={
                "title": "Pending complete",
                "author": "Author",
                "acquisition_date": "2025-03-10",
                "container_id": container["id"],
                "position": 1,
            },
        ).json()
        pending_unknown_acquisition = client.post(
            "/books",
            json={
                "title": "Pending unknown acquisition",
                "author": "Author",
                "is_original_collection": True,
            },
        ).json()
        client.post(
            "/books",
            json={
                "title": "Read complete",
                "author": "Author",
                "status": "READ",
                "acquisition_date": "2024-01-10",
                "reading_started_date": "2024-02-01",
                "read_date": "2024-02-05",
                "container_id": container["id"],
                "position": 2,
            },
        )
        read_unknown_finish = client.post(
            "/books",
            json={
                "title": "Read unknown finish",
                "author": "Author",
                "status": "READ",
                "acquisition_date": "2023-01-10",
                "is_read_date_unknown": True,
                "container_id": container["id"],
                "position": 3,
            },
        ).json()
        invalid_partial = client.post(
            "/books",
            json={
                "title": "Read missing start",
                "author": "Author",
                "status": "READ",
                "acquisition_date": "2022-01-10",
                "read_date": "2022-02-05",
                "container_id": container["id"],
                "position": 4,
            },
        )
        assert invalid_partial.status_code == 422
        covered = client.post(
            f'/books/{pending_complete["id"]}/cover',
            files={
                "cover": (
                    "pending.jpg",
                    image_bytes.getvalue(),
                    "image/jpeg",
                )
            },
        )
        assert covered.status_code == 200

        def titles_for(**params: object) -> set[str]:
            return {
                book["title"]
                for book in client.get("/books", params=params).json()
            }

        assert titles_for(quick_view="missing_finished") == {
            read_unknown_finish["title"]
        }
        assert titles_for(quick_view="original_collection") == {
            pending_unknown_acquisition["title"]
        }
        assert titles_for(catalogue_check="missing_started") == set()
        assert titles_for(catalogue_check="missing_end") == set()
        assert titles_for(catalogue_check="no_location") == {
            pending_unknown_acquisition["title"]
        }
        assert titles_for(catalogue_check="no_cover") == {
            "Pending unknown acquisition",
            "Read complete",
            "Read unknown finish",
        }
        date_range = {
            "date_field": "acquisition_date",
            "date_from": "2025-01-01",
            "date_to": "2025-12-31",
        }
        assert titles_for(**date_range) == {"Pending complete"}
        assert titles_for(
            **date_range,
            include_unknown_dates=True,
        ) == {
            "Pending complete",
            "Pending unknown acquisition",
        }
        assert titles_for(
            **date_range,
            include_unknown_sort_dates=True,
        ) == {"Pending complete"}
        acquisition_order_without_unknown = [
            book["title"]
            for book in client.get(
                "/books",
                params={
                    "sort_by": "acquisition_date",
                    "sort_order": "asc",
                },
            ).json()
        ]
        assert acquisition_order_without_unknown == [
            "Read unknown finish",
            "Read complete",
            "Pending complete",
        ]
        acquisition_order_with_unknown = [
            book["title"]
            for book in client.get(
                "/books",
                params={
                    "sort_by": "acquisition_date",
                    "sort_order": "asc",
                    "include_unknown_sort_dates": True,
                },
            ).json()
        ]
        assert acquisition_order_with_unknown == [
            "Pending unknown acquisition",
            "Read unknown finish",
            "Read complete",
            "Pending complete",
        ]
        reading_start_order = [
            book["title"]
            for book in client.get(
                "/books",
                params={
                    "sort_by": "reading_started_date",
                    "sort_order": "asc",
                },
            ).json()
        ]
        assert "Read missing start" not in reading_start_order
        assert "Pending unknown acquisition" not in reading_start_order


def test_catalogue_checks_find_missing_optional_bibliographic_metadata() -> None:
    complete_metadata = {
        "isbn_13": "9780306406157",
        "page_count": 300,
        "publisher": "Complete Press",
        "current_ed_year": 2024,
        "original_publication_year": 1999,
        "language": "English",
        "fiction_category": "FICTION",
        "binding": "PAPERBACK",
        "publication_type": "CONVENTIONAL_BOOK",
        "genre_text": "Mystery",
    }
    with TestClient(app) as client:
        complete = client.post(
            "/books",
            json={
                "title": "Complete metadata",
                "author": "Complete Author",
                **complete_metadata,
            },
        )
        missing_pages = client.post(
            "/books",
            json={
                "title": "Missing pages only",
                "author": "Partial Author",
                **{
                    key: value
                    for key, value in complete_metadata.items()
                    if key != "page_count"
                },
            },
        )
        assert complete.status_code == 201
        assert missing_pages.status_code == 201

        def titles(check: str) -> set[str]:
            return {
                book["title"]
                for book in client.get(
                    "/books", params={"catalogue_check": check}
                ).json()
            }

        assert titles("missing_metadata") == {"Missing pages only"}
        assert titles("missing_page_count") == {"Missing pages only"}
        assert titles("missing_isbn") == set()
        assert titles("missing_language") == set()


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


def test_occupied_position_can_shift_books_downward() -> None:
    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases", json={"name": "Downward Shift"}
        ).json()
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
        for position in (2, 4, 5, 6, 8):
            client.post(
                "/books",
                json={
                    "title": f"Book {position}",
                    "author": "Author",
                    "container_id": container["id"],
                    "position": position,
                },
            )

        conflict = client.post(
            "/books",
            json={
                "title": "New Six",
                "author": "Author",
                "container_id": container["id"],
                "position": 6,
                "shift_direction": "DOWN",
            },
        )
        assert conflict.status_code == 409
        detail = conflict.json()["detail"]
        assert detail["shift_direction"] == "DOWN"
        assert detail["shift_count"] == 3
        assert detail["last_position"] == 4
        assert detail["shift_possible"] is True

        inserted = client.post(
            "/books",
            json={
                "title": "New Six",
                "author": "Author",
                "container_id": container["id"],
                "position": 6,
                "shift_existing": True,
                "shift_direction": "DOWN",
            },
        )
        assert inserted.status_code == 201
        books = client.get(
            "/books",
            params={"container_id": container["id"], "sort_by": "physical"},
        ).json()
        assert [(book["title"], book["position"]) for book in books] == [
            ("Book 2", 2),
            ("Book 4", 3),
            ("Book 5", 4),
            ("Book 6", 5),
            ("New Six", 6),
            ("Book 8", 8),
        ]


def test_downward_shift_is_blocked_at_position_one() -> None:
    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases", json={"name": "Downward Boundary"}
        ).json()
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
        for position in (1, 2, 3):
            client.post(
                "/books",
                json={
                    "title": f"Book {position}",
                    "author": "Author",
                    "container_id": container["id"],
                    "position": position,
                },
            )

        conflict = client.post(
            "/books",
            json={
                "title": "New Three",
                "author": "Author",
                "container_id": container["id"],
                "position": 3,
                "shift_direction": "DOWN",
            },
        )
        assert conflict.status_code == 409
        assert conflict.json()["detail"]["shift_possible"] is False

        blocked = client.post(
            "/books",
            json={
                "title": "New Three",
                "author": "Author",
                "container_id": container["id"],
                "position": 3,
                "shift_existing": True,
                "shift_direction": "DOWN",
            },
        )
        assert blocked.status_code == 409
        assert blocked.json()["detail"]["code"] == "POSITION_SHIFT_BLOCKED"


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
                "acquisition_date": "2024-01-10",
                "page_count": 240,
                "language": "Galician",
                "current_ed_year": 2024,
                "original_publication_year": 1998,
                "fiction_category": "FICTION",
                "binding": "PAPERBACK",
                "publication_type": "CONVENTIONAL_BOOK",
                "genre_text": "Crime, Mystery",
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
                "acquisition_date": "2023-03-01",
                "reading_started_date": "2023-03-10",
                "read_date": "2023-03-20",
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
                "acquisition_date": "2025-05-01",
                "reading_started_date": "2025-05-04",
                "container_id": background["id"],
                "position": 3,
            },
        ).json()
        assert reading["container_id"] == background["id"]
        assert reading["position"] == 3

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
        assert (
            mapped_shelf["containers"][0]["books"][0]["acquisition_date"]
            == "2024-01-10"
        )
        mapped_book = mapped_shelf["containers"][0]["books"][0]
        assert mapped_book["page_count"] == 240
        assert mapped_book["language"] == "Galician"
        assert mapped_book["current_ed_year"] == 2024
        assert mapped_book["original_publication_year"] == 1998
        assert mapped_book["fiction_category"] == "FICTION"
        assert mapped_book["binding"] == "PAPERBACK"
        assert mapped_book["publication_type"] == "CONVENTIONAL_BOOK"
        assert mapped_book["genre_text"] == "Crime, Mystery"
        assert mapped_shelf["containers"][0]["status_counts"] == {
            "pending": 1,
            "reading": 0,
            "read": 0,
        }
        assert mapped_shelf["containers"][1]["status_counts"]["read"] == 1
        assert len(payload["outside_books"]) == 1
        outside = payload["outside_books"][0]
        assert outside["id"] == reading["id"]
        assert outside["title"] == "Reading away from shelf"
        assert outside["status"] == "CURRENTLY_READING"
        assert outside["container_id"] == background["id"]
        assert outside["position"] == 3
        assert outside["language"] is None
        assert outside["genre_text"] is None
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
        layout["containers"][0].update({"x": 8, "y": 12, "width": 40, "height": 70})
        saved = client.put("/visual-layout", json=layout)
        assert saved.status_code == 200
        assert saved.json()["bookcases"][0]["x"] == 11
        assert saved.json()["shelves"][0]["height_weight"] == 2.5
        assert saved.json()["containers"][0]["x"] == 8
        assert saved.json()["containers"][0]["y"] == 12
        assert saved.json()["containers"][0]["height"] == 70

        persisted = client.get("/library-map").json()["layout"]
        assert persisted == saved.json()

        invalid = persisted.copy()
        invalid["bookcases"] = [
            {**invalid["bookcases"][0], "x": 90, "width": 35}
        ]
        assert client.put("/visual-layout", json=invalid).status_code == 422


def test_visual_layout_prevents_overlap_within_the_same_shelf_layer() -> None:
    with TestClient(app) as client:
        bookcase = client.post(
            "/bookcases", json={"name": "Collision Bookcase"}
        ).json()
        shelf = client.post(
            "/shelves",
            json={"bookcase_id": bookcase["id"], "shelf_number": 1},
        ).json()
        background_row = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "ROW",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        ).json()
        background_pile = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "PILE",
                "layer": "BACKGROUND",
                "container_number": 1,
            },
        ).json()
        foreground = client.post(
            "/containers",
            json={
                "shelf_id": shelf["id"],
                "container_type": "ROW",
                "layer": "FOREGROUND",
                "container_number": 1,
            },
        ).json()

        layout = client.get("/library-map").json()["layout"]
        by_id = {item["id"]: item for item in layout["containers"]}
        by_id[background_row["id"]].update(
            {"x": 0, "y": 0, "width": 50, "height": 100}
        )
        by_id[background_pile["id"]].update(
            {"x": 40, "y": 0, "width": 50, "height": 100}
        )
        by_id[foreground["id"]].update(
            {"x": 0, "y": 0, "width": 100, "height": 100}
        )

        blocked = client.put("/visual-layout", json=layout)
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["code"] == "CONTAINER_LAYOUT_OVERLAP"
        assert set(blocked.json()["detail"]["container_ids"]) == {
            background_row["id"],
            background_pile["id"],
        }

        by_id[background_pile["id"]].update(
            {"x": 50, "y": 0, "width": 50, "height": 100}
        )
        allowed = client.put("/visual-layout", json=layout)
        assert allowed.status_code == 200
