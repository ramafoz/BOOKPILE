from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bookpile_server.models import Book, Library
from bookpile_server.repositories.books import BookRepository


def seed_two_libraries(session: Session) -> tuple[Library, Library]:
    first = Library(name="Home", slug=f"home-{uuid4().hex}")
    second = Library(name="Office", slug=f"office-{uuid4().hex}")
    session.add_all([first, second])
    session.flush()
    session.add_all(
        [
            Book(library_id=first.id, title="Piranesi", author="Susanna Clarke"),
            Book(library_id=second.id, title="Dune", author="Frank Herbert"),
        ]
    )
    session.commit()
    return first, second


def test_repository_requires_and_applies_library_scope(session: Session) -> None:
    first, second = seed_two_libraries(session)
    repository = BookRepository(session)

    first_books = repository.list_for_library(first.id)
    second_books = repository.list_for_library(second.id)

    assert [book.title for book in first_books] == ["Piranesi"]
    assert [book.title for book in second_books] == ["Dune"]


def test_catalogue_api_does_not_leak_another_library(
    client: TestClient, session: Session
) -> None:
    first, second = seed_two_libraries(session)

    response = client.get(f"/api/v1/libraries/{first.id}/catalogue")

    assert response.status_code == 200
    body = response.json()
    assert body["library_id"] == str(first.id)
    assert [book["title"] for book in body["books"]] == ["Piranesi"]
    assert "Dune" not in response.text

    second_response = client.get(f"/api/v1/libraries/{second.id}/catalogue")
    assert [book["title"] for book in second_response.json()["books"]] == [
        "Dune"
    ]


def test_unknown_library_returns_an_empty_scoped_catalogue(
    client: TestClient,
) -> None:
    missing_library_id = UUID(int=0)

    response = client.get(
        f"/api/v1/libraries/{missing_library_id}/catalogue"
    )

    assert response.status_code == 200
    assert response.json() == {
        "library_id": str(missing_library_id),
        "books": [],
    }


def test_health_identifies_server_edition(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "edition": "server",
    }

