from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import (
    Book,
    BookContributor,
    ContributorRole,
    Library,
    LibraryAuditEvent,
    LibraryMembership,
    User,
    UserSession,
)
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.auth import hash_session_secret


CSRF = "catalogue-services-csrf"
ROLES = [
    ("AUTHOR", "Author", 10),
    ("TRANSLATOR", "Translator", 30),
    ("ILLUSTRATOR", "Illustrator", 40),
]


def seed_roles(session: Session) -> None:
    session.add_all(
        [
            ContributorRole(code=code, label=label, sort_order=order)
            for code, label, order in ROLES
        ]
    )
    session.commit()


def add_user(session: Session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash=hash_password("valid catalogue password"),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user


def authenticate(client: TestClient, session: Session, user: User) -> None:
    token = f"catalogue-{uuid4().hex}"
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_secret(token),
            csrf_token_hash=hash_session_secret(CSRF),
            last_seen_at=now,
            expires_at=now + timedelta(days=1),
            absolute_expires_at=now + timedelta(days=7),
        )
    )
    session.commit()
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, token)
    client.cookies.set(settings.csrf_cookie_name, CSRF)


def csrf() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF}


def create_library_with_members(
    session: Session, owner: User, viewer: User | None = None
) -> Library:
    library = Library(name=f"Library {uuid4().hex[:6]}", slug=uuid4().hex)
    session.add(library)
    session.flush()
    session.add(
        LibraryMembership(library_id=library.id, user_id=owner.id, role="OWNER")
    )
    if viewer:
        session.add(
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
            )
        )
    session.commit()
    return library


def payload(title: str = "The Left Hand of Darkness") -> dict[str, object]:
    return {
        "title": title,
        "author": "Multiple authors",
        "isbn_10": "0-441-47812-3",
        "isbn_13": "9780441478125",
        "subtitle": "A novel",
        "page_count": 304,
        "publisher": "Ace Books",
        "current_ed_year": 2010,
        "original_publication_year": 1969,
        "language": "English",
        "original_language": "English",
        "translation_status": "ORIGINAL",
        "edition_number": 2,
        "fiction_category": "FICTION",
        "binding": "PAPERBACK",
        "publication_type": "CONVENTIONAL_BOOK",
        "genre_text": " Science Fiction ; Classic, science fiction ",
        "series_name": "Hainish Cycle",
        "series_volume": "4",
        "notes": "  Shared catalogue note  ",
        "acquisition_date": "2026-08-01",
        "is_original_collection": False,
        "height_mm": 198,
        "width_mm": 129,
        "thickness_mm": 22,
        "contributors": [
            {"role_code": "AUTHOR", "name": "Ursula K. Le Guin"},
            {"role_code": "AUTHOR", "name": "Guest Writer"},
            {"role_code": "ILLUSTRATOR", "name": "Cover Artist"},
        ],
    }


def test_owner_crud_normalizes_and_audits_complete_books(
    client: TestClient, session: Session
) -> None:
    seed_roles(session)
    owner = add_user(session, "catalogue_owner")
    library = create_library_with_members(session, owner)
    authenticate(client, session, owner)

    created = client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=payload(),
        headers=csrf(),
    )
    assert created.status_code == 201, created.text
    book = created.json()
    assert book["display_author"] == "Ursula K. Le Guin & Guest Writer"
    assert book["genre_text"] == "Classic, Science Fiction"
    assert book["notes"] == "Shared catalogue note"
    assert [item["position"] for item in book["contributors"]] == [1, 2, 1]
    assert book["height_mm"] == 198

    detail = client.get(
        f"/api/v1/libraries/{library.id}/catalogue/{book['id']}"
    )
    assert detail.status_code == 200
    assert detail.json()["isbn_13"] == "9780441478125"

    replacement = payload("The Dispossessed")
    replacement["author"] = "Ursula K. Le Guin"
    replacement["contributors"] = [
        {"role_code": "AUTHOR", "name": "Ursula K. Le Guin"},
        {"role_code": "TRANSLATOR", "name": "Translator Name"},
    ]
    updated = client.put(
        f"/api/v1/libraries/{library.id}/catalogue/{book['id']}",
        json=replacement,
        headers=csrf(),
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["display_author"] == "Ursula K. Le Guin"
    assert [item["role_code"] for item in updated.json()["contributors"]] == [
        "AUTHOR",
        "TRANSLATOR",
    ]

    wrong_confirmation = client.request(
        "DELETE",
        f"/api/v1/libraries/{library.id}/catalogue/{book['id']}",
        json={"confirmation_title": "Wrong title"},
        headers=csrf(),
    )
    assert wrong_confirmation.status_code == 422
    deleted = client.request(
        "DELETE",
        f"/api/v1/libraries/{library.id}/catalogue/{book['id']}",
        json={"confirmation_title": "The Dispossessed"},
        headers=csrf(),
    )
    assert deleted.status_code == 204
    assert session.get(Book, UUID(book["id"])) is None
    assert [
        event.event_type
        for event in session.scalars(
            select(LibraryAuditEvent).order_by(LibraryAuditEvent.id)
        )
    ] == ["book_created", "book_updated", "book_deleted"]


def test_viewer_reads_complete_catalogue_but_cannot_mutate(
    client: TestClient, session: Session
) -> None:
    seed_roles(session)
    owner = add_user(session, "viewer_test_owner")
    viewer = add_user(session, "read_only_viewer")
    library = create_library_with_members(session, owner, viewer)
    book = Book(library_id=library.id, title="Visible book", author="Visible author")
    session.add(book)
    session.commit()
    authenticate(client, session, viewer)

    listed = client.get(f"/api/v1/libraries/{library.id}/catalogue")
    assert listed.status_code == 200
    assert listed.json()["role"] == "VIEWER"
    assert listed.json()["can_edit"] is False
    assert client.get(
        f"/api/v1/libraries/{library.id}/catalogue/{book.id}"
    ).status_code == 200
    assert client.get(
        f"/api/v1/libraries/{library.id}/catalogue/metadata-options"
    ).status_code == 200

    assert client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=payload(),
        headers=csrf(),
    ).status_code == 404
    assert client.put(
        f"/api/v1/libraries/{library.id}/catalogue/{book.id}",
        json=payload(),
        headers=csrf(),
    ).status_code == 404
    assert client.request(
        "DELETE",
        f"/api/v1/libraries/{library.id}/catalogue/{book.id}",
        json={"confirmation_title": book.title},
        headers=csrf(),
    ).status_code == 404
    assert session.get(Book, book.id) is not None


def test_search_filters_options_and_counts_are_library_scoped(
    client: TestClient, session: Session
) -> None:
    seed_roles(session)
    owner = add_user(session, "filter_owner")
    library = create_library_with_members(session, owner)
    other = create_library_with_members(session, owner)
    authenticate(client, session, owner)
    first = client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=payload("Hainish One"),
        headers=csrf(),
    ).json()
    second_payload = payload("Another World")
    second_payload.update(
        {
            "author": "Solo Writer",
            "contributors": [{"role_code": "AUTHOR", "name": "Solo Writer"}],
            "language": "Galician",
            "original_language": "English",
            "translation_status": "TRANSLATED",
            "publisher": "Galaxia",
            "genre_text": "Fantasy",
            "series_name": None,
            "page_count": 180,
            "current_ed_year": 2024,
        }
    )
    client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=second_payload,
        headers=csrf(),
    )
    other_payload = payload("Secret Other Library")
    other_payload["publisher"] = "Hidden Publisher"
    client.post(
        f"/api/v1/libraries/{other.id}/catalogue",
        json=other_payload,
        headers=csrf(),
    )

    contributor_search = client.get(
        f"/api/v1/libraries/{library.id}/catalogue",
        params={"search": "Guest Writer"},
    ).json()
    assert contributor_search["total"] == 1
    assert contributor_search["books"][0]["id"] == first["id"]

    filtered = client.get(
        f"/api/v1/libraries/{library.id}/catalogue",
        params=[
            ("language", "Galician"),
            ("genre", "Fantasy"),
            ("page_max", "200"),
            ("year_min", "2020"),
            ("author_structure", "SINGLE"),
        ],
    ).json()
    assert filtered["total"] == 1
    assert filtered["books"][0]["title"] == "Another World"

    invalid_range = client.get(
        f"/api/v1/libraries/{library.id}/catalogue",
        params={"page_min": 500, "page_max": 100},
    )
    assert invalid_range.status_code == 422

    options = client.get(
        f"/api/v1/libraries/{library.id}/catalogue/metadata-options"
    ).json()
    assert options["languages"] == ["English", "Galician"]
    assert options["genres"] == ["Classic", "Fantasy", "Science Fiction"]
    assert "Hidden Publisher" not in options["publishers"]


def test_invalid_contributor_update_is_atomic(
    client: TestClient, session: Session
) -> None:
    seed_roles(session)
    owner = add_user(session, "atomic_owner")
    library = create_library_with_members(session, owner)
    authenticate(client, session, owner)
    created = client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=payload(),
        headers=csrf(),
    ).json()
    invalid = payload("Should not persist")
    invalid["contributors"] = [
        {"role_code": "UNKNOWN_ROLE", "name": "Someone"}
    ]
    invalid["author"] = "Someone"

    response = client.put(
        f"/api/v1/libraries/{library.id}/catalogue/{created['id']}",
        json=invalid,
        headers=csrf(),
    )
    assert response.status_code == 422
    session.expire_all()
    saved = session.get(Book, UUID(created["id"]))
    assert saved is not None and saved.title == "The Left Hand of Darkness"
    contributors = list(
        session.scalars(
            select(BookContributor).where(BookContributor.book_id == saved.id)
        )
    )
    assert len(contributors) == 3


def test_write_validation_rejects_invalid_isbn_translation_and_duplicates(
    client: TestClient, session: Session
) -> None:
    seed_roles(session)
    owner = add_user(session, "validation_owner")
    library = create_library_with_members(session, owner)
    authenticate(client, session, owner)

    invalid_isbn = payload()
    invalid_isbn["isbn_13"] = "9780000000000"
    assert client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=invalid_isbn,
        headers=csrf(),
    ).status_code == 422

    invalid_translation = payload()
    invalid_translation.update(
        {
            "translation_status": "TRANSLATED",
            "language": "English",
            "original_language": "English",
        }
    )
    assert client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=invalid_translation,
        headers=csrf(),
    ).status_code == 422

    duplicate = payload()
    duplicate["contributors"] = [
        {"role_code": "AUTHOR", "name": "Same Name"},
        {"role_code": "AUTHOR", "name": " same   name "},
    ]
    assert client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=duplicate,
        headers=csrf(),
    ).status_code == 422

    personal_review = payload()
    personal_review["goodreads_url"] = "https://www.goodreads.com/review/show/1"
    assert client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=personal_review,
        headers=csrf(),
    ).status_code == 422
