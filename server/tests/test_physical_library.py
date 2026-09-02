from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

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
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.auth import hash_session_secret


CSRF = "physical-library-csrf"


def add_user(session: Session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash=hash_password("valid physical library password"),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user


def add_library(
    session: Session,
    owner: User,
    viewer: User | None = None,
    *,
    viewer_scope: str = "CATALOG_AND_MAP",
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
                viewer_scope=viewer_scope,
            )
        )
    session.commit()
    return library


def authenticate(client: TestClient, session: Session, user: User) -> None:
    token = f"physical-{uuid4().hex}"
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


def base(library: Library) -> str:
    return f"/api/v1/libraries/{library.id}/physical-library"


def create_bookcase(client: TestClient, library: Library, name: str = "Office"):
    response = client.post(
        f"{base(library)}/bookcases",
        json={
            "name": name,
            "description": "North wall",
            "height_mm": 2000,
            "width_mm": 900,
            "depth_mm": 250,
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text
    return response.json()["bookcases"][-1]


def create_shelf(
    client: TestClient, library: Library, bookcase_id: str, number: int
):
    response = client.post(
        f"{base(library)}/shelves",
        json={
            "bookcase_id": bookcase_id,
            "shelf_number": number,
            "usable_height_mm": 300,
            "usable_width_mm": 850,
            "usable_depth_mm": 220,
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text
    return next(
        shelf
        for bookcase in response.json()["bookcases"]
        if bookcase["id"] == bookcase_id
        for shelf in bookcase["shelves"]
        if shelf["shelf_number"] == number
    )


def create_container(
    client: TestClient,
    library: Library,
    shelf_id: str,
    number: int,
    *,
    kind: str = "ROW",
    layer: str = "BACKGROUND",
):
    response = client.post(
        f"{base(library)}/containers",
        json={
            "shelf_id": shelf_id,
            "container_type": kind,
            "layer": layer,
            "container_number": number,
        },
        headers=csrf(),
    )
    assert response.status_code == 201, response.text
    return next(
        container
        for bookcase in response.json()["bookcases"]
        for shelf in bookcase["shelves"]
        if shelf["id"] == shelf_id
        for container in shelf["containers"]
        if container["container_type"] == kind
        and container["layer"] == layer
        and container["container_number"] == number
    )


def test_create_with_placement_is_atomic(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "atomic_placement_owner")
    library = add_library(session, owner)
    authenticate(client, session, owner)
    bookcase = create_bookcase(client, library, "Atomic room")
    shelf = create_shelf(client, library, bookcase["id"], 1)
    container = create_container(client, library, shelf["id"], 1)
    payload = {
        "book": {"title": "Atomic book", "author": "Careful Writer"},
        "placement": {"container_id": container["id"], "position": 1},
    }

    created = client.post(
        f"/api/v1/libraries/{library.id}/catalogue/with-placement",
        json=payload,
        headers=csrf(),
    )

    assert created.status_code == 201, created.text
    book = session.get(Book, UUID(created.json()["id"]))
    assert book is not None
    assert str(book.container_id) == container["id"]
    assert book.position == 1

    invalid = client.post(
        f"/api/v1/libraries/{library.id}/catalogue/with-placement",
        json={
            "book": {"title": "Must roll back", "author": "Careful Writer"},
            "placement": {"container_id": str(uuid4()), "position": 1},
        },
        headers=csrf(),
    )
    assert invalid.status_code == 422
    session.expire_all()
    assert session.scalar(
        select(Book).where(
            Book.library_id == library.id,
            Book.title == "Must roll back",
        )
    ) is None

    invalid_update = client.put(
        f"/api/v1/libraries/{library.id}/catalogue/{created.json()['id']}/with-placement",
        json={
            "book": {"title": "Changed but invalid", "author": "Careful Writer"},
            "placement": {"container_id": str(uuid4()), "position": 1},
        },
        headers=csrf(),
    )
    assert invalid_update.status_code == 422
    session.expire_all()
    unchanged = session.get(Book, UUID(created.json()["id"]))
    assert unchanged is not None
    assert unchanged.title == "Atomic book"
    assert str(unchanged.container_id) == container["id"]
    assert unchanged.position == 1


def test_owner_builds_and_renumbers_hierarchy_atomically(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "physical_owner")
    library = add_library(session, owner)
    authenticate(client, session, owner)

    bookcase = create_bookcase(client, library)
    first_shelf = create_shelf(client, library, bookcase["id"], 1)
    second_shelf = create_shelf(client, library, bookcase["id"], 2)

    swapped = client.put(
        f"{base(library)}/shelves/{second_shelf['id']}",
        json={
            "shelf_number": 1,
            "usable_height_mm": 310,
            "usable_width_mm": 860,
            "usable_depth_mm": 230,
        },
        headers=csrf(),
    )
    assert swapped.status_code == 200, swapped.text
    shelves = swapped.json()["bookcases"][0]["shelves"]
    assert [(item["id"], item["shelf_number"]) for item in shelves] == [
        (second_shelf["id"], 1),
        (first_shelf["id"], 2),
    ]

    row_one = create_container(client, library, second_shelf["id"], 1)
    row_two = create_container(client, library, second_shelf["id"], 2)
    pile_one = create_container(
        client, library, second_shelf["id"], 1, kind="PILE"
    )
    assert pile_one["container_number"] == row_one["container_number"]

    swapped_rows = client.put(
        f"{base(library)}/containers/{row_two['id']}",
        json={"container_number": 1},
        headers=csrf(),
    )
    assert swapped_rows.status_code == 200, swapped_rows.text
    containers = swapped_rows.json()["bookcases"][0]["shelves"][0]["containers"]
    rows = [item for item in containers if item["container_type"] == "ROW"]
    assert [(item["id"], item["container_number"]) for item in rows] == [
        (row_two["id"], 1),
        (row_one["id"], 2),
    ]

    duplicate = client.post(
        f"{base(library)}/containers",
        json={
            "shelf_id": second_shelf["id"],
            "container_type": "ROW",
            "layer": "BACKGROUND",
            "container_number": 1,
        },
        headers=csrf(),
    )
    assert duplicate.status_code == 409

    events = list(
        session.scalars(
            select(LibraryAuditEvent)
            .where(LibraryAuditEvent.library_id == library.id)
            .order_by(LibraryAuditEvent.occurred_at)
        )
    )
    assert {event.event_type for event in events} >= {
        "bookcase_created",
        "shelf_created",
        "shelf_updated",
        "container_created",
        "container_updated",
    }


def test_map_scope_is_enforced_and_viewers_cannot_write(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "scope_owner")
    viewer = add_user(session, "scope_viewer")
    outsider = add_user(session, "scope_outsider")
    library = add_library(session, owner, viewer)
    authenticate(client, session, owner)
    create_bookcase(client, library, "Shared map")

    authenticate(client, session, viewer)
    visible = client.get(base(library))
    assert visible.status_code == 200
    assert visible.json()["role"] == "VIEWER"
    assert visible.json()["can_edit"] is False
    denied_write = client.post(
        f"{base(library)}/bookcases",
        json={"name": "Viewer furniture"},
        headers=csrf(),
    )
    assert denied_write.status_code == 404

    membership = session.scalar(
        select(LibraryMembership).where(
            LibraryMembership.library_id == library.id,
            LibraryMembership.user_id == viewer.id,
        )
    )
    assert membership is not None
    membership.viewer_scope = "CATALOG_ONLY"
    session.commit()
    assert client.get(base(library)).status_code == 404

    authenticate(client, session, outsider)
    assert client.get(base(library)).status_code == 404


def test_cross_library_parents_and_nonempty_deletions_are_rejected(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "guard_owner")
    first_library = add_library(session, owner)
    second_library = add_library(session, owner)
    authenticate(client, session, owner)

    first_bookcase = create_bookcase(client, first_library, "First room")
    other_bookcase = create_bookcase(client, second_library, "Second room")
    cross_library = client.post(
        f"{base(first_library)}/shelves",
        json={"bookcase_id": other_bookcase["id"], "shelf_number": 1},
        headers=csrf(),
    )
    assert cross_library.status_code == 404

    shelf = create_shelf(client, first_library, first_bookcase["id"], 1)
    container = create_container(client, first_library, shelf["id"], 1)
    book = Book(
        library_id=first_library.id,
        title="Placed book",
        author="Author",
        container_id=UUID(container["id"]),
        position=1,
    )
    session.add(book)
    session.commit()

    confirmed = {"confirmed": True}
    assert client.request(
        "DELETE",
        f"{base(first_library)}/containers/{container['id']}",
        json=confirmed,
        headers=csrf(),
    ).status_code == 409
    assert client.request(
        "DELETE",
        f"{base(first_library)}/shelves/{shelf['id']}",
        json=confirmed,
        headers=csrf(),
    ).status_code == 409
    assert client.request(
        "DELETE",
        f"{base(first_library)}/bookcases/{first_bookcase['id']}",
        json=confirmed,
        headers=csrf(),
    ).status_code == 409

    book.container_id = None
    book.position = None
    session.commit()
    assert client.request(
        "DELETE",
        f"{base(first_library)}/containers/{container['id']}",
        json=confirmed,
        headers=csrf(),
    ).status_code == 204
    assert client.request(
        "DELETE",
        f"{base(first_library)}/shelves/{shelf['id']}",
        json=confirmed,
        headers=csrf(),
    ).status_code == 204
    assert client.request(
        "DELETE",
        f"{base(first_library)}/bookcases/{first_bookcase['id']}",
        json=confirmed,
        headers=csrf(),
    ).status_code == 204


def test_book_placement_squeezes_destination_and_compacts_source(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "placement_owner")
    library = add_library(session, owner)
    authenticate(client, session, owner)
    bookcase = create_bookcase(client, library, "Placement room")
    shelf = create_shelf(client, library, bookcase["id"], 1)
    first = create_container(client, library, shelf["id"], 1)
    second = create_container(client, library, shelf["id"], 2)
    books = [
        Book(library_id=library.id, title=f"Book {number}", author="Author")
        for number in range(1, 5)
    ]
    session.add_all(books)
    session.commit()

    def place(book: Book, container_id: str | None, position: int | None):
        return client.put(
            f"{base(library)}/books/{book.id}/placement",
            json={"container_id": container_id, "position": position},
            headers=csrf(),
        )

    assert place(books[0], first["id"], 1).status_code == 200
    assert place(books[1], first["id"], 2).status_code == 200
    inserted = place(books[2], first["id"], 1)
    assert inserted.status_code == 200, inserted.text
    response_books = {item["id"]: item for item in inserted.json()["books"]}
    assert [response_books[str(book.id)]["position"] for book in books[:3]] == [2, 3, 1]

    moved = place(books[2], second["id"], 1)
    assert moved.status_code == 200, moved.text
    response_books = {item["id"]: item for item in moved.json()["books"]}
    assert [response_books[str(book.id)]["position"] for book in books[:3]] == [1, 2, 1]

    removed = place(books[0], None, None)
    assert removed.status_code == 200, removed.text
    response_books = {item["id"]: item for item in removed.json()["books"]}
    assert response_books[str(books[0].id)]["container_id"] is None
    assert response_books[str(books[1].id)]["position"] == 1

    gap = place(books[3], first["id"], 3)
    assert gap.status_code == 422
    assert "cannot contain gaps" in gap.json()["detail"]

    other_library = add_library(session, owner)
    other_bookcase = create_bookcase(client, other_library, "Other room")
    other_shelf = create_shelf(client, other_library, other_bookcase["id"], 1)
    other_container = create_container(client, other_library, other_shelf["id"], 1)
    assert place(books[3], other_container["id"], 1).status_code == 404

    nonempty_delete = client.request(
        "DELETE",
        f"{base(library)}/containers/{second['id']}",
        json={"confirmed": True},
        headers=csrf(),
    )
    assert nonempty_delete.status_code == 409

    events = list(
        session.scalars(
            select(LibraryAuditEvent).where(
                LibraryAuditEvent.library_id == library.id,
                LibraryAuditEvent.event_type == "book_placement_updated",
            )
        )
    )
    assert len(events) == 5


def test_rearrangement_preview_is_read_only_and_apply_checks_revision(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "rearrangement_owner")
    library = add_library(session, owner)
    authenticate(client, session, owner)
    bookcase = create_bookcase(client, library, "Rearrangement room")
    shelf = create_shelf(client, library, bookcase["id"], 1)
    row = create_container(client, library, shelf["id"], 1)
    books = [
        Book(
            library_id=library.id,
            title=f"Move {number}",
            author="Author",
            container_id=UUID(row["id"]),
            position=number,
        )
        for number in range(1, 4)
    ]
    session.add_all(books)
    session.commit()
    request = {
        "book_id": str(books[0].id),
        "old_position_mode": "COLLAPSE",
        "release_shelf_space": False,
        "steps": [{
            "container_id": row["id"],
            "position": 3,
            "new_position_mode": "SQUEEZE",
        }],
        "completed_operations": [],
    }

    preview = client.post(
        f"{base(library)}/rearrangements/preview", json=request
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_to_apply"] is True
    session.expire_all()
    assert [session.get(Book, item.id).position for item in books] == [1, 2, 3]

    stale = client.post(
        f"{base(library)}/rearrangements/apply",
        json={**request, "revision": "0" * 64},
        headers=csrf(),
    )
    assert stale.status_code == 409

    applied = client.post(
        f"{base(library)}/rearrangements/apply",
        json={**request, "revision": preview.json()["revision"]},
        headers=csrf(),
    )
    assert applied.status_code == 200, applied.text
    session.expire_all()
    assert [session.get(Book, item.id).position for item in books] == [3, 1, 2]
    event = session.scalar(
        select(LibraryAuditEvent).where(
            LibraryAuditEvent.library_id == library.id,
            LibraryAuditEvent.event_type == "books_rearranged",
        )
    )
    assert event is not None


def test_visual_layout_saves_explicit_anchor_support_and_rejects_stale_writes(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "layout_owner")
    library = add_library(session, owner)
    authenticate(client, session, owner)
    bookcase = create_bookcase(client, library, "Visual room")
    shelf = create_shelf(client, library, bookcase["id"], 1)
    row = create_container(client, library, shelf["id"], 1)
    pile = create_container(client, library, shelf["id"], 1, kind="PILE")
    session.add(
        Book(
            library_id=library.id,
            title="Supporting book",
            author="Author",
            container_id=UUID(row["id"]),
            position=1,
        )
    )
    session.commit()

    initial = client.get(base(library))
    assert initial.status_code == 200, initial.text
    layout = initial.json()["layout"]
    assert len(layout["bookcases"]) == 1
    assert len(layout["shelves"]) == 1
    pile_layout = next(
        item for item in layout["containers"] if item["container_id"] == pile["id"]
    )
    assert pile_layout["support_kind"] == "SHELF"

    row_layout = next(
        item for item in layout["containers"] if item["container_id"] == row["id"]
    )
    # Background containers may be offset from the shelf bottom to create the
    # established visual depth effect.
    row_layout.update({"x": 0, "y": 60, "width": 100, "height": 30, "row_anchor": "RIGHT"})
    pile_layout.update(
        {
            "x": 0,
            "y": 10,
            "width": 50,
            "height": 50,
            "support_kind": "CONTAINER",
            "support_container_id": row["id"],
        }
    )
    saved = client.put(f"{base(library)}/layout", json=layout, headers=csrf())
    assert saved.status_code == 200, saved.text
    saved_layout = saved.json()["layout"]
    saved_row = next(
        item for item in saved_layout["containers"] if item["container_id"] == row["id"]
    )
    saved_pile = next(
        item for item in saved_layout["containers"] if item["container_id"] == pile["id"]
    )
    assert saved_row["row_anchor"] == "RIGHT"
    assert saved_pile["support_kind"] == "CONTAINER"
    assert saved_pile["support_container_id"] == row["id"]

    stale = client.put(f"{base(library)}/layout", json=layout, headers=csrf())
    assert stale.status_code == 409
    assert "changed after you opened" in stale.json()["detail"]

    invalid = saved_layout
    invalid_pile = next(
        item for item in invalid["containers"] if item["container_id"] == pile["id"]
    )
    invalid_pile["support_container_id"] = str(uuid4())
    rejected = client.put(f"{base(library)}/layout", json=invalid, headers=csrf())
    assert rejected.status_code == 422
    assert "same shelf and layer" in rejected.json()["detail"]

    event = session.scalar(
        select(LibraryAuditEvent).where(
            LibraryAuditEvent.library_id == library.id,
            LibraryAuditEvent.event_type == "visual_layout_updated",
        )
    )
    assert event is not None
