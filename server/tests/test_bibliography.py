from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest

from bookpile_server.api.routes import catalogue as catalogue_routes
from bookpile_server.bibliography import BibliographicProvidersUnavailable, lookup_isbn
from bookpile_server.config import get_settings
from bookpile_server.models import Book, Library, LibraryMembership, User, UserSession
from bookpile_server.services.auth import hash_session_secret


def _client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_lookup_normalizes_open_library_metadata() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, request=request, json={
            "key": "/books/OL1M", "title": " Example  Book ",
            "authors": [{"name": "First Author"}, {"name": "Second Author"}],
            "isbn_10": ["0-306-40615-2"], "isbn_13": ["9780306406157"],
            "publishers": ["Example Press"], "publish_date": "2001",
            "number_of_pages": 320, "languages": [{"key": "/languages/eng"}],
            "subjects": ["Fiction"],
        })

    with _client(handler) as client:
        candidate = lookup_isbn("978-0-306-40615-7", client=client)[0]

    assert candidate["title"] == "Example Book"
    assert candidate["authors"] == ["First Author", "Second Author"]
    assert candidate["identifiers"] == {"isbn_10": "0306406152", "isbn_13": "9780306406157"}
    assert candidate["language"] == "English"
    assert candidate["fiction_category"] == "FICTION"


def test_lookup_uses_google_fallback_and_normalizes_outage() -> None:
    def fallback(request: httpx.Request) -> httpx.Response:
        if request.url.host == "openlibrary.org":
            return httpx.Response(404, request=request)
        return httpx.Response(200, request=request, json={"items": [{
            "id": "g1", "volumeInfo": {"title": "Fallback", "authors": ["Writer"]}
        }]})

    with _client(fallback) as client:
        assert lookup_isbn("9780306406157", client=client)[0]["source"] == "GOOGLE_BOOKS"

    with _client(lambda request: httpx.Response(503, request=request)) as client:
        with pytest.raises(BibliographicProvidersUnavailable):
            lookup_isbn("9780306406157", client=client)


def _authenticate(client, session, *, role: str = "OWNER") -> tuple[Library, User]:
    now = datetime.now(UTC)
    library = Library(name="Home", slug=f"home-{uuid4().hex}")
    user = User(email=f"scan-{uuid4().hex}@example.test", username=f"scan_{uuid4().hex[:8]}", password_hash="unused", state="active", email_verified_at=now)
    session.add_all([library, user]); session.flush()
    session.add(LibraryMembership(library_id=library.id, user_id=user.id, role=role, viewer_scope="CATALOG_AND_MAP" if role == "VIEWER" else None, selected_reading_user_id=user.id if role == "OWNER" else None))
    token = f"scan-{uuid4().hex}"
    session.add(UserSession(user_id=user.id, token_hash=hash_session_secret(token), csrf_token_hash=hash_session_secret("csrf"), last_seen_at=now, expires_at=now + timedelta(days=7), absolute_expires_at=now + timedelta(days=30)))
    session.commit(); client.cookies.set(get_settings().session_cookie_name, token)
    return library, user


def test_server_isbn_lookup_is_owner_only_and_library_scoped(client, session, monkeypatch) -> None:
    library, _ = _authenticate(client, session)
    session.add(Book(library_id=library.id, title="Stored copy", author="Writer", isbn_13="9780306406157")); session.commit()
    monkeypatch.setattr(catalogue_routes, "lookup_isbn", lambda isbn: [{
        "source": "TEST", "source_record_id": "one",
        "identifiers": {"isbn_10": None, "isbn_13": isbn}, "title": "Provider copy",
        "subtitle": None, "authors": ["Writer"], "publisher": None,
        "current_ed_year": None, "original_publication_year": None, "page_count": None,
        "subjects": [], "language": None, "edition_number": None,
        "fiction_category": None, "binding": None, "publication_type": None,
        "genre_text": None, "series_name": None, "series_volume": None,
        "confidence_or_match_notes": None, "catalogue_matches": [],
    }])

    response = client.get(f"/api/v1/libraries/{library.id}/catalogue/isbn-lookup", params={"isbn": "978-0-306-40615-7"})
    assert response.status_code == 200
    assert response.json()["isbn"] == "9780306406157"
    assert response.json()["catalogue_matches"][0]["title"] == "Stored copy"
    assert response.json()["candidates"][0]["catalogue_matches"][0]["book_id"] == response.json()["catalogue_matches"][0]["book_id"]

    invalid = client.get(f"/api/v1/libraries/{library.id}/catalogue/isbn-lookup", params={"isbn": "9780306406158"})
    assert invalid.status_code == 422


def test_viewer_cannot_use_bibliographic_lookup(client, session, monkeypatch) -> None:
    library, _ = _authenticate(client, session, role="VIEWER")
    monkeypatch.setattr(catalogue_routes, "lookup_isbn", lambda isbn: pytest.fail("provider must not be called"))
    response = client.get(f"/api/v1/libraries/{library.id}/catalogue/isbn-lookup", params={"isbn": "9780306406157"})
    assert response.status_code == 404
