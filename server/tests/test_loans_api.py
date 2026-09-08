from datetime import UTC, datetime, timedelta
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


CSRF = "loan-api-csrf"


def make_user(session: Session, name: str) -> User:
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


def authenticate(client: TestClient, session: Session, user: User) -> None:
    raw = f"loan-{uuid4().hex}"
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=user.id,
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
    first = make_user(session, "loan_owner_one")
    second = make_user(session, "loan_owner_two")
    viewer = make_user(session, "loan_viewer")
    map_viewer = make_user(session, "loan_map_viewer")
    outsider = make_user(session, "loan_outsider")
    library = Library(name="Loan library", slug=f"loan-{uuid4().hex}")
    other = Library(name="Other", slug=f"other-loan-{uuid4().hex}")
    session.add_all([library, other])
    session.flush()
    session.add_all(
        [
            LibraryMembership(library_id=library.id, user_id=first.id, role="OWNER"),
            LibraryMembership(library_id=library.id, user_id=second.id, role="OWNER"),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=map_viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_AND_MAP",
            ),
            LibraryMembership(library_id=other.id, user_id=outsider.id, role="OWNER"),
        ]
    )
    book = Book(library_id=library.id, title="Shared copy", author="Author")
    session.add(book)
    session.commit()
    return library, book, first, second, viewer, map_viewer, outsider


def url(library: Library, book: Book) -> str:
    return f"/api/v1/libraries/{library.id}/catalogue/{book.id}/loans"


def test_owner_lifecycle_is_shared_and_audit_redacts_sensitive_text(
    client: TestClient, session: Session
) -> None:
    library, book, first, second, _, _, _ = shared_fixture(session)
    endpoint = url(library, book)
    authenticate(client, session, first)

    assert client.post(endpoint + "/active", json={"loaned_to": "Alice"}).status_code == 403
    started = client.post(
        endpoint + "/active",
        headers=headers(),
        json={
            "loaned_to": "  Alice Example  ",
            "notes": "  private address  ",
            "loaned_date": "2026-09-01",
            "expected_return_date": "2026-09-20",
        },
    )
    assert started.status_code == 201, started.text
    assert started.json()["loaned_to"] == "Alice Example"
    assert started.json()["notes"] == "private address"
    assert client.post(endpoint + "/active", headers=headers(), json={"loaned_to": "Bob"}).status_code == 409

    authenticate(client, session, second)
    shared = client.get(endpoint)
    assert shared.status_code == 200
    assert shared.json()["access"] == "OWNER"
    assert shared.json()["loans"][0]["loaned_to"] == "Alice Example"
    returned = client.post(
        endpoint + "/active/return",
        headers=headers(),
        json={"returned_date": "2026-09-05"},
    )
    assert returned.status_code == 200, returned.text

    historical = client.post(
        endpoint + "/history",
        headers=headers(),
        json={"loaned_to": "Unknown old borrower", "notes": "secret"},
    )
    assert historical.status_code == 201, historical.text
    history_id = historical.json()["id"]
    edited = client.put(
        endpoint + f"/{history_id}",
        headers=headers(),
        json={
            "loaned_to": "Corrected borrower",
            "loaned_date": "2020-01-01",
            "returned_date": "2020-01-02",
        },
    )
    assert edited.status_code == 200, edited.text
    assert client.delete(endpoint + f"/{history_id}", headers=headers()).status_code == 204

    events = list(
        session.scalars(
            select(LibraryAuditEvent).where(
                LibraryAuditEvent.event_type.like("loan.%")
            )
        )
    )
    assert {event.event_type for event in events} >= {
        "loan.started",
        "loan.returned",
        "loan.historical_added",
        "loan.historical_edited",
        "loan.historical_deleted",
    }
    assert all(set(event.details) == {"book_id", "loan_id"} for event in events)
    assert "Alice" not in repr([event.details for event in events])
    assert "secret" not in repr([event.details for event in events])


def test_viewer_projection_omits_borrower_and_notes_and_cannot_write(
    client: TestClient, session: Session
) -> None:
    library, book, owner, _, viewer, map_viewer, outsider = shared_fixture(session)
    endpoint = url(library, book)
    authenticate(client, session, owner)
    assert client.post(
        endpoint + "/active",
        headers=headers(),
        json={"loaned_to": "Never disclose", "notes": "private"},
    ).status_code == 201

    authenticate(client, session, viewer)
    response = client.get(endpoint)
    assert response.status_code == 200
    payload = response.json()
    assert payload["access"] == "VIEWER"
    assert payload["writable"] is False
    assert "loaned_to" not in payload["loans"][0]
    assert "notes" not in payload["loans"][0]
    overview = client.get(f"/api/v1/libraries/{library.id}/loan-overview")
    assert overview.status_code == 200
    assert overview.json()["total_active"] == 1
    assert "loaned_to" not in overview.json()["loans"][0]
    assert "notes" not in overview.json()["loans"][0]
    assert overview.json()["loans"][0]["book_id"] == str(book.id)
    assert client.post(
        endpoint + "/active/return", headers=headers(), json={}
    ).status_code == 403

    authenticate(client, session, map_viewer)
    map_scope = client.get(endpoint)
    assert map_scope.status_code == 200
    assert "loaned_to" not in map_scope.text
    assert "private" not in map_scope.text
    other_library = session.scalar(
        select(Library).where(Library.id != library.id)
    )
    assert other_library is not None
    other_book = Book(
        library_id=other_library.id, title="Other copy", author="Other"
    )
    session.add(other_book)
    session.commit()
    assert client.get(
        f"/api/v1/libraries/{library.id}/catalogue/{other_book.id}/loans"
    ).status_code == 404

    authenticate(client, session, outsider)
    assert client.get(endpoint).status_code == 404


def test_loan_catalogue_filters_and_statistics(
    client: TestClient, session: Session
) -> None:
    library, book, owner, _, viewer, _, _ = shared_fixture(session)
    authenticate(client, session, owner)
    assert client.post(
        url(library, book) + "/active",
        headers=headers(),
        json={"loaned_to": "Visible only to owners", "loaned_date": "2026-09-01"},
    ).status_code == 201
    catalogue = f"/api/v1/libraries/{library.id}/catalogue"
    assert client.get(catalogue, params={"loan_scope": "ACTIVE"}).json()["total"] == 1
    assert client.get(catalogue, params={"available_only": "true"}).json()["total"] == 0
    assert client.get(catalogue, params={"loaned_to": "Visible"}).json()["total"] == 1
    statistics = client.get(f"/api/v1/libraries/{library.id}/loan-overview/statistics")
    assert statistics.status_code == 200
    assert statistics.json()["active"] == 1
    assert statistics.json()["books"][0]["book_id"] == str(book.id)

    authenticate(client, session, viewer)
    assert client.get(catalogue, params={"loaned_to": "Visible"}).status_code == 403
    assert client.get(f"/api/v1/libraries/{library.id}/loan-overview/statistics").status_code == 200


def test_active_loan_blocks_new_reading_but_existing_reading_allows_later_loan(
    client: TestClient, session: Session
) -> None:
    library, book, first, _, _, _, _ = shared_fixture(session)
    endpoint = url(library, book)
    reading = endpoint.removesuffix("/loans") + "/reading"
    authenticate(client, session, first)
    assert client.post(
        endpoint + "/active",
        headers=headers(),
        json={"loaned_to": "Alice"},
    ).status_code == 201
    blocked = client.post(
        reading + "/sessions/start",
        headers=headers(),
        json={"started_date": "2026-09-01"},
    )
    assert blocked.status_code == 409
    assert client.delete(endpoint + "/active", headers=headers()).status_code == 204
    assert client.post(
        reading + "/sessions/start",
        headers=headers(),
        json={"started_date": "2026-09-01"},
    ).status_code == 201
    # Agreed rule: loaning an already-being-read copy is allowed.
    assert client.post(
        endpoint + "/active",
        headers=headers(),
        json={"loaned_to": "Bob"},
    ).status_code == 201
