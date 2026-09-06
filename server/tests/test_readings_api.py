from datetime import UTC, date, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import (
    Book,
    Library,
    LibraryAuditEvent,
    LibraryMembership,
    User,
    UserSession,
)
from bookpile_server.services.auth import hash_session_secret


CSRF = "reading-api-csrf"


def user(session: Session, name: str) -> User:
    item = User(
        email=f"{name}@example.test",
        username=name,
        password_hash="not-used",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(item)
    session.commit()
    return item


def authenticate(client: TestClient, session: Session, item: User) -> None:
    raw = f"reading-{uuid4().hex}"
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=item.id,
            token_hash=hash_session_secret(raw),
            csrf_token_hash=hash_session_secret(CSRF),
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
            absolute_expires_at=now + timedelta(days=7),
        )
    )
    session.commit()
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, raw)
    client.cookies.set(settings.csrf_cookie_name, CSRF)


def headers() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF}


def shared_fixture(session: Session):
    first = user(session, "reader_one")
    second = user(session, "reader_two")
    viewer = user(session, "reading_viewer")
    outsider = user(session, "reading_outsider")
    library = Library(name="Reading library", slug=f"reading-{uuid4().hex}")
    other = Library(name="Other", slug=f"other-{uuid4().hex}")
    session.add_all([library, other])
    session.flush()
    session.add_all(
        [
            LibraryMembership(
                library_id=library.id,
                user_id=first.id,
                role="OWNER",
                selected_reading_user_id=first.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=second.id,
                role="OWNER",
                selected_reading_user_id=second.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
                selected_reading_user_id=first.id,
            ),
            LibraryMembership(
                library_id=other.id,
                user_id=outsider.id,
                role="OWNER",
                selected_reading_user_id=outsider.id,
            ),
        ]
    )
    book = Book(library_id=library.id, title="Shared copy", author="Author")
    session.add(book)
    session.commit()
    return library, book, first, second, viewer, outsider


def reading_url(library: Library, book: Book) -> str:
    return f"/api/v1/libraries/{library.id}/catalogue/{book.id}/reading"


def test_personal_perspectives_and_single_shared_active_copy(
    client: TestClient, session: Session
) -> None:
    library, book, first, second, viewer, outsider = shared_fixture(session)
    url = reading_url(library, book)
    authenticate(client, session, first)

    pending = client.get(url)
    assert pending.status_code == 200
    assert pending.json() | {"sessions": []} == pending.json()
    assert pending.json()["state"] == "PENDING"
    assert pending.json()["writable"] is True

    assert client.post(
        f"{url}/sessions/start", json={"started_date": "2026-09-01"}
    ).status_code == 403
    started = client.post(
        f"{url}/sessions/start",
        json={"started_date": "2026-09-01"},
        headers=headers(),
    )
    assert started.status_code == 201, started.text
    first_session = started.json()["id"]
    assert client.get(url).json()["state"] == "READING"

    authenticate(client, session, second)
    own_view = client.get(url).json()
    assert own_view["state"] == "PENDING"
    assert own_view["active_reader_present"] is True
    first_view = client.get(url, params={"perspective_user_id": first.id}).json()
    assert first_view["state"] == "READING"
    assert first_view["writable"] is False
    assert client.post(
        f"{url}/sessions/{first_session}/finish",
        json={"finished_date": "2026-09-03"},
        headers=headers(),
    ).status_code == 404
    conflict = client.post(
        f"{url}/sessions/start",
        json={"started_date": "2026-09-02"},
        headers=headers(),
    )
    assert conflict.status_code == 409

    authenticate(client, session, viewer)
    assert client.get(url).json()["state"] == "READING"
    assert client.post(
        f"{url}/sessions/start",
        json={"started_date": "2026-09-02"},
        headers=headers(),
    ).status_code == 403

    authenticate(client, session, outsider)
    assert client.get(url).status_code == 404

    authenticate(client, session, first)
    invalid_finish = client.post(
        f"{url}/sessions/{first_session}/finish",
        json={"finished_date": "2026-08-31"},
        headers=headers(),
    )
    assert invalid_finish.status_code == 422
    assert client.get(url).json()["state"] == "READING"
    finished = client.post(
        f"{url}/sessions/{first_session}/finish",
        json={"finished_date": "2026-09-03"},
        headers=headers(),
    )
    assert finished.status_code == 200, finished.text
    assert client.get(url).json()["state"] == "READ"
    reread = client.post(
        f"{url}/sessions/start",
        json={"started_date": "2026-09-03"},
        headers=headers(),
    )
    assert reread.status_code == 201
    assert client.get(url).json()["state"] == "REREADING"
    assert client.delete(
        f"{url}/sessions/{reread.json()['id']}/cancel", headers=headers()
    ).status_code == 204
    assert client.get(url).json()["state"] == "READ"


def test_historical_crud_validation_and_personal_goodreads(
    client: TestClient, session: Session
) -> None:
    library, book, first, second, viewer, _ = shared_fixture(session)
    url = reading_url(library, book)
    authenticate(client, session, first)

    unknown = client.post(
        f"{url}/sessions/historical",
        json={"dates_unknown": True},
        headers=headers(),
    )
    assert unknown.status_code == 201, unknown.text
    assert client.post(
        f"{url}/sessions/historical",
        json={"dates_unknown": True},
        headers=headers(),
    ).status_code == 422
    known = client.post(
        f"{url}/sessions/historical",
        json={
            "started_date": "2025-01-10",
            "finished_date": "2025-01-12",
            "dates_unknown": False,
        },
        headers=headers(),
    )
    assert known.status_code == 201, known.text
    assert client.post(
        f"{url}/sessions/historical",
        json={
            "started_date": "2025-01-11",
            "finished_date": "2025-01-13",
        },
        headers=headers(),
    ).status_code == 422
    edited = client.put(
        f"{url}/sessions/{known.json()['id']}",
        json={
            "started_date": "2025-02-01",
            "finished_date": "2025-02-01",
        },
        headers=headers(),
    )
    assert edited.status_code == 200, edited.text
    assert edited.json()["started_date"] == "2025-02-01"

    evil = client.put(
        f"{url}/goodreads/me",
        json={"url": "https://goodreads.com.evil.example/review/1"},
        headers=headers(),
    )
    assert evil.status_code == 422
    first_review = client.put(
        f"{url}/goodreads/me",
        json={"url": "https://www.goodreads.com/review/show/1"},
        headers=headers(),
    )
    assert first_review.status_code == 200, first_review.text
    assert first_review.json()["username"] == first.username

    authenticate(client, session, second)
    assert client.put(
        f"{url}/goodreads/me",
        json={"url": "https://goodreads.com/review/show/2"},
        headers=headers(),
    ).status_code == 200

    authenticate(client, session, viewer)
    reviews = client.get(f"{url}/goodreads")
    assert reviews.status_code == 200
    assert [(item["username"], item["url"]) for item in reviews.json()] == [
        (first.username, "https://www.goodreads.com/review/show/1"),
        (second.username, "https://goodreads.com/review/show/2"),
    ]
    assert client.put(
        f"{url}/goodreads/me", json={"url": None}, headers=headers()
    ).status_code == 403

    authenticate(client, session, first)
    assert client.delete(
        f"{url}/sessions/{known.json()['id']}", headers=headers()
    ).status_code == 204
    projection = client.get(url).json()
    assert len(projection["sessions"]) == 1
    assert projection["total_sessions"] == 1
    page = client.get(url, params={"limit": 1, "offset": 0}).json()
    assert page["limit"] == 1
    assert page["offset"] == 0
    assert len(page["sessions"]) == 1
    events = list(session.scalars(select(LibraryAuditEvent)))
    assert {event.event_type for event in events} >= {
        "reading.historical_added",
        "reading.edited",
        "reading.deleted",
        "personal_book.goodreads_changed",
    }
