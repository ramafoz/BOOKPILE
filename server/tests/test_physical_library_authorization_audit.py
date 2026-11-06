from collections.abc import Callable
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import (
    Book,
    Bookcase,
    Container,
    LibraryAuditEvent,
    LibraryMembership,
    Shelf,
    VisualBookcaseLayout,
    VisualContainerLayout,
    VisualShelfLayout,
)
from test_physical_library import (
    add_library,
    add_user,
    authenticate,
    base,
    create_bookcase,
    create_container,
    create_shelf,
    csrf,
)


def _authenticate(client: TestClient, session: Session, actor) -> None:
    client.cookies.clear()
    authenticate(client, session, actor)


def _snapshot(session: Session) -> dict[str, tuple[tuple[Any, ...], ...]]:
    session.expire_all()

    def rows(model: type[Any]) -> tuple[tuple[Any, ...], ...]:
        values = session.execute(select(*model.__table__.columns)).all()
        return tuple(sorted((tuple(value) for value in values), key=repr))

    return {
        "books": rows(Book),
        "bookcases": rows(Bookcase),
        "shelves": rows(Shelf),
        "containers": rows(Container),
        "bookcase_layouts": rows(VisualBookcaseLayout),
        "shelf_layouts": rows(VisualShelfLayout),
        "container_layouts": rows(VisualContainerLayout),
        "audit": rows(LibraryAuditEvent),
    }


def test_physical_map_and_rearrangement_authorization_matrix(
    client: TestClient,
    session: Session,
) -> None:
    first_owner = add_user(session, "a4_first_owner")
    second_owner = add_user(session, "a4_second_owner")
    catalogue_viewer = add_user(session, "a4_catalogue_viewer")
    map_viewer = add_user(session, "a4_map_viewer")
    library = add_library(
        session,
        first_owner,
        catalogue_viewer,
        viewer_scope="CATALOG_ONLY",
    )
    session.add_all(
        (
            LibraryMembership(
                library_id=library.id,
                user_id=second_owner.id,
                role="OWNER",
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=map_viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_AND_MAP",
            ),
        )
    )
    session.commit()

    _authenticate(client, session, first_owner)
    bookcase = create_bookcase(client, library, "A4 shared room")
    shelf = create_shelf(client, library, bookcase["id"], 1)
    container = create_container(client, library, shelf["id"], 1)
    books = [
        Book(
            library_id=library.id,
            title=f"A4 book {position}",
            author="A4 author",
            container_id=UUID(container["id"]),
            position=position,
        )
        for position in range(1, 4)
    ]
    session.add_all(books)
    session.commit()

    rearrangement = {
        "book_id": str(books[0].id),
        "old_position_mode": "COLLAPSE",
        "release_shelf_space": False,
        "steps": [
            {
                "container_id": container["id"],
                "position": 3,
                "new_position_mode": "SQUEEZE",
            }
        ],
        "completed_operations": [],
    }

    _authenticate(client, session, second_owner)
    owner_map = client.get(base(library))
    assert owner_map.status_code == 200
    assert owner_map.json()["role"] == "OWNER"
    assert owner_map.json()["can_edit"] is True
    before_preview = _snapshot(session)
    preview = client.post(
        f"{base(library)}/rearrangements/preview",
        json=rearrangement,
    )
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid_to_apply"] is True
    assert _snapshot(session) == before_preview
    applied = client.post(
        f"{base(library)}/rearrangements/apply",
        json={**rearrangement, "revision": preview.json()["revision"]},
        headers=csrf(),
    )
    assert applied.status_code == 200, applied.text
    session.expire_all()
    assert [session.get(Book, book.id).position for book in books] == [3, 1, 2]

    for viewer, can_see_map in (
        (catalogue_viewer, False),
        (map_viewer, True),
    ):
        _authenticate(client, session, viewer)
        projection = client.get(base(library))
        if can_see_map:
            assert projection.status_code == 200
            assert projection.json()["role"] == "VIEWER"
            assert projection.json()["can_edit"] is False
            assert len(projection.json()["bookcases"]) == 1
            assert len(projection.json()["books"]) == 3
            layout_payload = projection.json()["layout"]
        else:
            assert projection.status_code == 404
            layout_payload = owner_map.json()["layout"]

        baseline = _snapshot(session)
        forbidden: tuple[tuple[str, Callable[[], Any]], ...] = (
            (
                "create bookcase",
                lambda: client.post(
                    f"{base(library)}/bookcases",
                    json={"name": "Forbidden furniture"},
                    headers=csrf(),
                ),
            ),
            (
                "update bookcase",
                lambda: client.put(
                    f"{base(library)}/bookcases/{bookcase['id']}",
                    json={"name": "Forbidden rename"},
                    headers=csrf(),
                ),
            ),
            (
                "delete bookcase",
                lambda: client.request(
                    "DELETE",
                    f"{base(library)}/bookcases/{bookcase['id']}",
                    json={"confirmed": True},
                    headers=csrf(),
                ),
            ),
            (
                "create shelf",
                lambda: client.post(
                    f"{base(library)}/shelves",
                    json={"bookcase_id": bookcase["id"], "shelf_number": 2},
                    headers=csrf(),
                ),
            ),
            (
                "update container",
                lambda: client.put(
                    f"{base(library)}/containers/{container['id']}",
                    json={"container_number": 2},
                    headers=csrf(),
                ),
            ),
            (
                "move book",
                lambda: client.put(
                    f"{base(library)}/books/{books[0].id}/placement",
                    json={"container_id": None, "position": None},
                    headers=csrf(),
                ),
            ),
            (
                "save visual layout",
                lambda: client.put(
                    f"{base(library)}/layout",
                    json=layout_payload,
                    headers=csrf(),
                ),
            ),
            (
                "preview rearrangement",
                lambda: client.post(
                    f"{base(library)}/rearrangements/preview",
                    json=rearrangement,
                ),
            ),
            (
                "apply rearrangement",
                lambda: client.post(
                    f"{base(library)}/rearrangements/apply",
                    json={**rearrangement, "revision": preview.json()["revision"]},
                    headers=csrf(),
                ),
            ),
        )
        for label, attempt in forbidden:
            response = attempt()
            assert response.status_code == 404, (label, response.text)
            assert _snapshot(session) == baseline, label
