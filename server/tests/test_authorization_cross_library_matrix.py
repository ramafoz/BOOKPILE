from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import (
    Book,
    Bookcase,
    Container,
    Library,
    LibraryAuditEvent,
    LibraryImportJob,
    LibraryInvitation,
    LibraryMembership,
    Loan,
    ReadingSession,
    Shelf,
    User,
    UserSession,
)
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.auth import hash_session_secret


CSRF = "a1-cross-library-csrf"
PASSWORD = "valid A1 cross-library password"


@dataclass(frozen=True)
class Actor:
    user: User
    raw_session: str
    role: str
    library: Library
    foreign_library: Library


@dataclass(frozen=True)
class LibraryResources:
    library: Library
    owner: User
    viewer: User
    book: Book
    reading: ReadingSession
    loan: Loan
    bookcase: Bookcase
    shelf: Shelf
    container: Container
    invitation: LibraryInvitation
    import_job: LibraryImportJob


@dataclass(frozen=True)
class AuthorizationWorld:
    actors: tuple[Actor, ...]
    resources: dict[UUID, LibraryResources]


@dataclass(frozen=True)
class ForeignRequest:
    family: str
    method: str
    url: str
    json: dict[str, Any] | None = None


def _user(session: Session, name: str) -> User:
    item = User(
        email=f"{name}@example.test",
        username=name,
        password_hash=hash_password(PASSWORD),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(item)
    session.flush()
    return item


def _session(session: Session, user: User) -> str:
    raw = f"a1-{user.username}-{uuid4().hex}"
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
    return raw


def _library_resources(
    session: Session,
    *,
    label: str,
    viewer_scope: str,
) -> tuple[LibraryResources, str, str]:
    owner = _user(session, f"a1_owner_{label}")
    viewer = _user(session, f"a1_viewer_{label}")
    library = Library(
        name=f"A1 library {label}",
        slug=f"a1-{label}-{uuid4().hex}",
        created_by_user_id=owner.id,
    )
    session.add(library)
    session.flush()
    session.add_all(
        [
            LibraryMembership(
                library_id=library.id,
                user_id=owner.id,
                role="OWNER",
                selected_reading_user_id=owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope=viewer_scope,
                selected_reading_user_id=owner.id,
            ),
        ]
    )

    bookcase = Bookcase(library_id=library.id, name=f"Case {label}")
    session.add(bookcase)
    session.flush()
    shelf = Shelf(
        library_id=library.id,
        bookcase_id=bookcase.id,
        shelf_number=1,
    )
    session.add(shelf)
    session.flush()
    container = Container(
        library_id=library.id,
        shelf_id=shelf.id,
        container_type="ROW",
        layer="BACKGROUND",
        container_number=1,
    )
    session.add(container)
    session.flush()
    book = Book(
        library_id=library.id,
        title=f"Private book {label}",
        author=f"Private author {label}",
        container_id=container.id,
        position=1,
    )
    session.add(book)
    session.flush()
    reading = ReadingSession(
        library_id=library.id,
        book_id=book.id,
        user_id=owner.id,
        state="COMPLETED",
        started_date=date(2026, 1, 1),
        finished_date=date(2026, 1, 2),
        dates_unknown=False,
    )
    loan = Loan(
        library_id=library.id,
        book_id=book.id,
        state="RETURNED",
        loaned_to=f"Private borrower {label}",
        notes=f"Private loan note {label}",
        loaned_date=date(2026, 1, 3),
        returned_date=date(2026, 1, 4),
    )
    invitation = LibraryInvitation(
        library_id=library.id,
        token_hash=uuid4().hex + uuid4().hex,
        role="VIEWER",
        viewer_scope="CATALOG_ONLY",
        created_by_user_id=owner.id,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    import_job = LibraryImportJob(
        library_id=library.id,
        created_by_user_id=owner.id,
        reading_owner_user_id=owner.id,
        state="READY",
        adapter="bookpile-local",
        backup_format_version=1,
        local_schema_version=1,
        source_created_at="2026-01-01T00:00:00Z",
        archive_sha256=("a" if label == "a" else "b") * 64,
        source_fingerprint=("c" if label == "a" else "d") * 64,
        staging_sha256=("e" if label == "a" else "f") * 64,
        staging_key=f"a1-staging-{label}-{uuid4().hex}",
        source_counts={},
        source_kind="LOCAL",
        source_library_name=f"Private source {label}",
        source_members=[],
        warnings=[],
        archive_bytes=1,
        uncompressed_bytes=1,
        estimated_logical_bytes=1,
        capacity_available=True,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    session.add_all([reading, loan, invitation, import_job])
    session.flush()

    return (
        LibraryResources(
            library=library,
            owner=owner,
            viewer=viewer,
            book=book,
            reading=reading,
            loan=loan,
            bookcase=bookcase,
            shelf=shelf,
            container=container,
            invitation=invitation,
            import_job=import_job,
        ),
        _session(session, owner),
        _session(session, viewer),
    )


@pytest.fixture
def authorization_world(session: Session) -> AuthorizationWorld:
    resources_a, owner_session_a, viewer_session_a = _library_resources(
        session,
        label="a",
        viewer_scope="CATALOG_ONLY",
    )
    resources_b, owner_session_b, viewer_session_b = _library_resources(
        session,
        label="b",
        viewer_scope="CATALOG_AND_MAP",
    )
    session.commit()
    return AuthorizationWorld(
        actors=(
            Actor(
                resources_a.owner,
                owner_session_a,
                "OWNER",
                resources_a.library,
                resources_b.library,
            ),
            Actor(
                resources_a.viewer,
                viewer_session_a,
                "VIEWER",
                resources_a.library,
                resources_b.library,
            ),
            Actor(
                resources_b.owner,
                owner_session_b,
                "OWNER",
                resources_b.library,
                resources_a.library,
            ),
            Actor(
                resources_b.viewer,
                viewer_session_b,
                "VIEWER",
                resources_b.library,
                resources_a.library,
            ),
        ),
        resources={
            resources_a.library.id: resources_a,
            resources_b.library.id: resources_b,
        },
    )


def _authenticate(client: TestClient, actor: Actor) -> None:
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, actor.raw_session)
    client.cookies.set(settings.csrf_cookie_name, CSRF)


def _requests(actor: Actor, foreign: LibraryResources) -> tuple[ForeignRequest, ...]:
    own_id = actor.library.id
    foreign_id = foreign.library.id
    own_catalogue = f"/api/v1/libraries/{own_id}/catalogue"
    foreign_catalogue = f"/api/v1/libraries/{foreign_id}/catalogue"
    own_physical = f"/api/v1/libraries/{own_id}/physical-library"
    return (
        ForeignRequest("library", "GET", f"/api/v1/libraries/{foreign_id}/members"),
        ForeignRequest(
            "library",
            "DELETE",
            f"/api/v1/libraries/{foreign_id}",
            {
                "current_password": PASSWORD,
                "confirmation_name": foreign.library.name,
                "acknowledge_permanent_deletion": True,
            },
        ),
        ForeignRequest(
            "library-membership",
            "PATCH",
            f"/api/v1/libraries/{own_id}/members/{foreign.viewer.id}",
            {"action": "REMOVE", "current_password": PASSWORD},
        ),
        ForeignRequest("catalogue", "GET", f"{own_catalogue}/{foreign.book.id}"),
        ForeignRequest(
            "catalogue",
            "PUT",
            f"{own_catalogue}/{foreign.book.id}",
            {"title": "Unauthorized rewrite", "author": "Unauthorized actor"},
        ),
        ForeignRequest("private-cover", "GET", f"{own_catalogue}/{foreign.book.id}/cover"),
        ForeignRequest("private-cover", "DELETE", f"{own_catalogue}/{foreign.book.id}/cover"),
        ForeignRequest(
            "reading",
            "GET",
            f"{own_catalogue}/{foreign.book.id}/reading",
        ),
        ForeignRequest(
            "reading",
            "DELETE",
            f"{own_catalogue}/{foreign.book.id}/reading/sessions/{foreign.reading.id}",
        ),
        ForeignRequest(
            "loan",
            "GET",
            f"{own_catalogue}/{foreign.book.id}/loans",
        ),
        ForeignRequest(
            "loan",
            "DELETE",
            f"{own_catalogue}/{foreign.book.id}/loans/{foreign.loan.id}",
        ),
        ForeignRequest("physical-library", "GET", f"/api/v1/libraries/{foreign_id}/physical-library"),
        ForeignRequest(
            "bookcase",
            "PUT",
            f"{own_physical}/bookcases/{foreign.bookcase.id}",
            {"name": "Unauthorized case"},
        ),
        ForeignRequest(
            "shelf",
            "PUT",
            f"{own_physical}/shelves/{foreign.shelf.id}",
            {"shelf_number": 2},
        ),
        ForeignRequest(
            "container",
            "PUT",
            f"{own_physical}/containers/{foreign.container.id}",
            {"container_number": 2},
        ),
        ForeignRequest(
            "placement",
            "PUT",
            f"{own_physical}/books/{foreign.book.id}/placement",
            {"container_id": str(foreign.container.id), "position": 2},
        ),
        ForeignRequest(
            "invitation",
            "DELETE",
            f"/api/v1/libraries/{own_id}/invitations/{foreign.invitation.id}",
        ),
        ForeignRequest(
            "import-job",
            "GET",
            f"/api/v1/libraries/{own_id}/imports/{foreign.import_job.id}",
        ),
        ForeignRequest(
            "import-job",
            "DELETE",
            f"/api/v1/libraries/{own_id}/imports/{foreign.import_job.id}",
        ),
        ForeignRequest("portable-export", "GET", f"/api/v1/libraries/{foreign_id}/exports/portable"),
        ForeignRequest("foreign-catalogue", "GET", foreign_catalogue),
    )


def _snapshot(session: Session) -> dict[str, tuple[tuple[Any, ...], ...]]:
    def rows(model: type[Any], *columns: Any) -> tuple[tuple[Any, ...], ...]:
        values = session.execute(select(*columns).select_from(model)).all()
        return tuple(sorted((tuple(value) for value in values), key=repr))

    return {
        "libraries": rows(
            Library,
            Library.id,
            Library.name,
            Library.state,
            Library.geometry_mode,
        ),
        "memberships": rows(
            LibraryMembership,
            LibraryMembership.id,
            LibraryMembership.library_id,
            LibraryMembership.user_id,
            LibraryMembership.role,
            LibraryMembership.viewer_scope,
        ),
        "books": rows(
            Book,
            Book.id,
            Book.library_id,
            Book.title,
            Book.author,
            Book.container_id,
            Book.position,
        ),
        "readings": rows(
            ReadingSession,
            ReadingSession.id,
            ReadingSession.library_id,
            ReadingSession.book_id,
            ReadingSession.state,
        ),
        "loans": rows(
            Loan,
            Loan.id,
            Loan.library_id,
            Loan.book_id,
            Loan.state,
            Loan.loaned_to,
            Loan.notes,
        ),
        "bookcases": rows(Bookcase, Bookcase.id, Bookcase.library_id, Bookcase.name),
        "shelves": rows(
            Shelf,
            Shelf.id,
            Shelf.library_id,
            Shelf.bookcase_id,
            Shelf.shelf_number,
        ),
        "containers": rows(
            Container,
            Container.id,
            Container.library_id,
            Container.shelf_id,
            Container.container_number,
        ),
        "invitations": rows(
            LibraryInvitation,
            LibraryInvitation.id,
            LibraryInvitation.library_id,
            LibraryInvitation.revoked_at,
            LibraryInvitation.consumed_at,
        ),
        "imports": rows(
            LibraryImportJob,
            LibraryImportJob.id,
            LibraryImportJob.library_id,
            LibraryImportJob.state,
            LibraryImportJob.result_counts,
        ),
        "audit": rows(
            LibraryAuditEvent,
            LibraryAuditEvent.id,
            LibraryAuditEvent.library_id,
            LibraryAuditEvent.event_type,
            LibraryAuditEvent.details,
        ),
    }


def test_valid_foreign_uuids_are_generically_denied_without_state_change(
    client: TestClient,
    session: Session,
    authorization_world: AuthorizationWorld,
) -> None:
    initial = _snapshot(session)
    exercised: set[tuple[str, str]] = set()

    for actor in authorization_world.actors:
        _authenticate(client, actor)
        foreign = authorization_world.resources[actor.foreign_library.id]
        private_markers = {
            str(foreign.library.id),
            str(foreign.book.id),
            foreign.book.title,
            foreign.loan.loaned_to,
            foreign.loan.notes or "",
        }
        for request in _requests(actor, foreign):
            response = client.request(
                request.method,
                request.url,
                json=request.json,
                headers={"X-CSRF-Token": CSRF},
            )
            assert response.status_code in {403, 404}, (
                actor.user.username,
                request.family,
                request.method,
                request.url,
                response.status_code,
                response.text,
            )
            if request.method == "GET" or actor.role == "OWNER":
                assert response.status_code == 404, (
                    actor.user.username,
                    request.family,
                    response.status_code,
                    response.text,
                )
            response_text = response.text
            assert not any(
                marker and marker in response_text for marker in private_markers
            ), (actor.user.username, request.family, response_text)
            session.expire_all()
            assert _snapshot(session) == initial, (
                actor.user.username,
                request.family,
                request.method,
            )
            exercised.add((request.family, request.method))

    assert exercised == {
        ("library", "GET"),
        ("library", "DELETE"),
        ("library-membership", "PATCH"),
        ("catalogue", "GET"),
        ("catalogue", "PUT"),
        ("private-cover", "GET"),
        ("private-cover", "DELETE"),
        ("reading", "GET"),
        ("reading", "DELETE"),
        ("loan", "GET"),
        ("loan", "DELETE"),
        ("physical-library", "GET"),
        ("bookcase", "PUT"),
        ("shelf", "PUT"),
        ("container", "PUT"),
        ("placement", "PUT"),
        ("invitation", "DELETE"),
        ("import-job", "GET"),
        ("import-job", "DELETE"),
        ("portable-export", "GET"),
        ("foreign-catalogue", "GET"),
    }
