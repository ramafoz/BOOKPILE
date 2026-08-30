from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import Book, Library, LibraryMembership, User, UserSession
from bookpile_server.repositories.books import BookRepository
from bookpile_server.services.auth import hash_session_secret


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


def authenticate(
    client: TestClient, session: Session, *, username: str
) -> User:
    now = datetime.now(UTC)
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash="not-used-by-catalogue-tests",
        state="active",
        email_verified_at=now,
    )
    session.add(user)
    session.flush()
    raw_token = f"catalogue-test-{uuid4().hex}"
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_secret(raw_token),
            csrf_token_hash=hash_session_secret("catalogue-test-csrf"),
            last_seen_at=now,
            expires_at=now + timedelta(days=7),
            absolute_expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    client.cookies.set(get_settings().session_cookie_name, raw_token)
    return user


def add_membership(
    session: Session,
    *,
    library: Library,
    user: User,
    role: str = "OWNER",
    viewer_scope: str | None = None,
) -> None:
    session.add(
        LibraryMembership(
            library_id=library.id,
            user_id=user.id,
            role=role,
            viewer_scope=viewer_scope,
            selected_reading_user_id=user.id if role == "OWNER" else None,
        )
    )
    session.commit()


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
    first_user = authenticate(client, session, username="first_reader")
    second_user = User(
        email="second_reader@example.test",
        username="second_reader",
        password_hash="not-used-by-catalogue-tests",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(second_user)
    session.flush()
    add_membership(session, library=first, user=first_user)
    add_membership(session, library=second, user=second_user)

    response = client.get(f"/api/v1/libraries/{first.id}/catalogue")

    assert response.status_code == 200
    body = response.json()
    assert body["library_id"] == str(first.id)
    assert body["total"] == 1
    assert body["limit"] == 50
    assert body["offset"] == 0
    assert [book["title"] for book in body["books"]] == ["Piranesi"]
    assert "Dune" not in response.text

    second_response = client.get(f"/api/v1/libraries/{second.id}/catalogue")
    assert second_response.status_code == 404
    assert "Dune" not in second_response.text


def test_unknown_library_is_hidden_from_authenticated_users(
    client: TestClient, session: Session
) -> None:
    authenticate(client, session, username="missing_reader")
    missing_library_id = uuid4()

    response = client.get(
        f"/api/v1/libraries/{missing_library_id}/catalogue"
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Library not found"}


def test_catalogue_requires_authentication(
    client: TestClient, session: Session
) -> None:
    first, _ = seed_two_libraries(session)

    response = client.get(f"/api/v1/libraries/{first.id}/catalogue")

    assert response.status_code == 401


def test_search_count_and_pagination_remain_library_scoped(
    client: TestClient, session: Session
) -> None:
    first, second = seed_two_libraries(session)
    user = authenticate(client, session, username="search_reader")
    add_membership(session, library=first, user=user)
    session.add_all(
        [
            Book(library_id=first.id, title="Dune Messiah", author="Frank Herbert"),
            Book(library_id=first.id, title="The Left Hand", author="Ursula Le Guin"),
            Book(library_id=second.id, title="Another Dune", author="Other Author"),
        ]
    )
    session.commit()

    response = client.get(
        f"/api/v1/libraries/{first.id}/catalogue",
        params={"search": "dune", "limit": 1, "offset": 0},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 1
    assert body["limit"] == 1
    assert [book["title"] for book in body["books"]] == ["Dune Messiah"]
    assert "Another Dune" not in response.text

    empty_page = client.get(
        f"/api/v1/libraries/{first.id}/catalogue",
        params={"search": "dune", "limit": 1, "offset": 1},
    ).json()
    assert empty_page["total"] == 1
    assert empty_page["books"] == []


def test_health_identifies_server_edition(client: TestClient) -> None:
    assert client.get("/health").json() == {
        "status": "ok",
        "edition": "server",
    }

