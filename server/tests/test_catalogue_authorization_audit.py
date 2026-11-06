from dataclasses import dataclass
from pathlib import Path
from collections.abc import Callable
from typing import Any
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import (
    Book,
    BookContributor,
    BookCover,
    Library,
    LibraryAuditEvent,
    LibraryMembership,
    User,
)
from test_catalogue_services import (
    add_user,
    authenticate,
    create_library_with_members,
    csrf,
    payload,
    seed_roles,
)
from test_private_covers import image_bytes


@dataclass(frozen=True)
class CatalogueAuthorizationWorld:
    owner: User
    catalogue_viewer: User
    map_viewer: User
    library: Library
    book_id: UUID
    cover_content: bytes
    storage_root: Path


@pytest.fixture
def catalogue_authorization_world(
    client: TestClient,
    session: Session,
    tmp_path: Path,
) -> CatalogueAuthorizationWorld:
    seed_roles(session)
    owner = add_user(session, "a2_owner")
    catalogue_viewer = add_user(session, "a2_catalogue_viewer")
    map_viewer = add_user(session, "a2_map_viewer")
    library = create_library_with_members(session, owner, catalogue_viewer)
    map_membership = LibraryMembership(
        library_id=library.id,
        user_id=map_viewer.id,
        role="VIEWER",
        viewer_scope="CATALOG_AND_MAP",
    )
    session.add(map_membership)
    session.commit()

    authenticate(client, session, owner)
    created = client.post(
        f"/api/v1/libraries/{library.id}/catalogue",
        json=payload("A2 protected catalogue book"),
        headers=csrf(),
    )
    assert created.status_code == 201, created.text
    book_id = UUID(created.json()["id"])
    cover_content = image_bytes(size=(80, 120), colour="navy", format="PNG")
    uploaded = client.put(
        f"/api/v1/libraries/{library.id}/catalogue/{book_id}/cover",
        files={"cover": ("a2-cover.png", cover_content, "image/png")},
        headers=csrf(),
    )
    assert uploaded.status_code == 200, uploaded.text
    fetched = client.get(
        f"/api/v1/libraries/{library.id}/catalogue/{book_id}/cover"
    )
    assert fetched.status_code == 200

    return CatalogueAuthorizationWorld(
        owner=owner,
        catalogue_viewer=catalogue_viewer,
        map_viewer=map_viewer,
        library=library,
        book_id=book_id,
        cover_content=fetched.content,
        storage_root=tmp_path / "private-objects",
    )


def _authenticate(client: TestClient, session: Session, user: User) -> None:
    client.cookies.clear()
    authenticate(client, session, user)


def _database_snapshot(session: Session) -> dict[str, tuple[tuple[Any, ...], ...]]:
    def rows(model: type[Any], *columns: Any) -> tuple[tuple[Any, ...], ...]:
        values = session.execute(select(*columns).select_from(model)).all()
        return tuple(sorted((tuple(value) for value in values), key=repr))

    return {
        "books": rows(
            Book,
            Book.id,
            Book.library_id,
            Book.title,
            Book.author,
            Book.notes,
            Book.updated_at,
        ),
        "contributors": rows(
            BookContributor,
            BookContributor.id,
            BookContributor.library_id,
            BookContributor.book_id,
            BookContributor.role_code,
            BookContributor.name,
            BookContributor.normalized_name,
            BookContributor.position,
        ),
        "covers": rows(
            BookCover,
            BookCover.id,
            BookCover.library_id,
            BookCover.book_id,
            BookCover.object_key,
            BookCover.byte_size,
            BookCover.sha256,
            BookCover.uploaded_by_user_id,
            BookCover.updated_at,
        ),
        "audit": rows(
            LibraryAuditEvent,
            LibraryAuditEvent.id,
            LibraryAuditEvent.library_id,
            LibraryAuditEvent.actor_user_id,
            LibraryAuditEvent.event_type,
            LibraryAuditEvent.details,
        ),
    }


def _stored_objects(root: Path) -> tuple[tuple[str, bytes], ...]:
    if not root.exists():
        return ()
    return tuple(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in sorted(item for item in root.rglob("*") if item.is_file())
    )


def _snapshot(
    session: Session,
    world: CatalogueAuthorizationWorld,
) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], tuple[tuple[str, bytes], ...]]:
    session.expire_all()
    return _database_snapshot(session), _stored_objects(world.storage_root)


def _assert_safe_catalogue_response(response_text: str) -> None:
    for forbidden in (
        "object_key",
        "uploaded_by_user_id",
        "sha256",
        "token_hash",
        "password_hash",
    ):
        assert forbidden not in response_text


def _assert_metadata_options(payload: dict[str, Any]) -> None:
    assert payload["languages"] == ["English"]
    assert payload["original_languages"] == ["English"]
    assert payload["publishers"] == ["Ace Books"]
    assert payload["genres"] == ["Classic", "Science Fiction"]
    assert payload["series_names"] == ["Hainish Cycle"]
    assert {item["code"] for item in payload["contributor_roles"]} == {
        "AUTHOR",
        "TRANSLATOR",
        "ILLUSTRATOR",
    }


def test_owner_can_manage_catalogue_contributors_metadata_and_private_cover(
    client: TestClient,
    session: Session,
    catalogue_authorization_world: CatalogueAuthorizationWorld,
) -> None:
    world = catalogue_authorization_world
    _authenticate(client, session, world.owner)
    catalogue_url = f"/api/v1/libraries/{world.library.id}/catalogue"
    book_url = f"{catalogue_url}/{world.book_id}"
    cover_url = f"{book_url}/cover"

    listed = client.get(catalogue_url)
    detail = client.get(book_url)
    metadata = client.get(f"{catalogue_url}/metadata-options")
    cover = client.get(cover_url)
    assert listed.status_code == 200
    assert listed.json()["role"] == "OWNER"
    assert listed.json()["can_edit"] is True
    assert detail.status_code == 200
    assert detail.json()["contributors"]
    assert metadata.status_code == 200
    _assert_metadata_options(metadata.json())
    assert cover.status_code == 200
    assert cover.content == world.cover_content
    for response in (listed, detail, metadata):
        _assert_safe_catalogue_response(response.text)

    replacement = payload("A2 owner-updated book")
    replacement["author"] = "Owner Updated Author"
    replacement["contributors"] = [
        {"role_code": "AUTHOR", "name": "Owner Updated Author"},
        {"role_code": "TRANSLATOR", "name": "Owner Translator"},
    ]
    updated = client.put(book_url, json=replacement, headers=csrf())
    assert updated.status_code == 200, updated.text
    assert updated.json()["title"] == "A2 owner-updated book"
    assert [
        (item["role_code"], item["name"])
        for item in updated.json()["contributors"]
    ] == [
        ("AUTHOR", "Owner Updated Author"),
        ("TRANSLATOR", "Owner Translator"),
    ]

    replacement_cover = image_bytes(size=(90, 130), colour="red", format="PNG")
    replaced = client.put(
        cover_url,
        files={"cover": ("replacement.png", replacement_cover, "image/png")},
        headers=csrf(),
    )
    assert replaced.status_code == 200, replaced.text
    replaced_bytes = client.get(cover_url).content
    assert replaced_bytes != world.cover_content

    temporary = client.post(
        catalogue_url,
        json=payload("A2 temporary owner book"),
        headers=csrf(),
    )
    assert temporary.status_code == 201, temporary.text
    temporary_id = temporary.json()["id"]
    removed = client.request(
        "DELETE",
        f"{catalogue_url}/{temporary_id}",
        json={"confirmation_title": "A2 temporary owner book"},
        headers=csrf(),
    )
    assert removed.status_code == 204

    cover_removed = client.delete(cover_url, headers=csrf())
    assert cover_removed.status_code == 204
    assert client.get(cover_url).status_code == 404
    restored = client.put(
        cover_url,
        files={"cover": ("restored.png", replacement_cover, "image/png")},
        headers=csrf(),
    )
    assert restored.status_code == 200, restored.text

    events = list(
        session.scalars(
            select(LibraryAuditEvent.event_type).where(
                LibraryAuditEvent.library_id == world.library.id
            )
        )
    )
    for expected in (
        "book_created",
        "book_updated",
        "book_deleted",
        "cover_uploaded",
        "cover_replaced",
        "cover_removed",
    ):
        assert expected in events


@pytest.mark.parametrize(
    "viewer_attribute",
    ("catalogue_viewer", "map_viewer"),
)
def test_both_viewer_scopes_read_shared_catalogue_but_cannot_change_it(
    viewer_attribute: str,
    client: TestClient,
    session: Session,
    catalogue_authorization_world: CatalogueAuthorizationWorld,
) -> None:
    world = catalogue_authorization_world
    viewer = getattr(world, viewer_attribute)
    _authenticate(client, session, viewer)
    catalogue_url = f"/api/v1/libraries/{world.library.id}/catalogue"
    book_url = f"{catalogue_url}/{world.book_id}"
    cover_url = f"{book_url}/cover"

    listed = client.get(catalogue_url)
    detail = client.get(book_url)
    metadata = client.get(f"{catalogue_url}/metadata-options")
    cover = client.get(cover_url)
    assert listed.status_code == 200
    assert listed.json()["role"] == "VIEWER"
    assert listed.json()["can_edit"] is False
    assert detail.status_code == 200
    assert detail.json()["title"] == "A2 protected catalogue book"
    assert detail.json()["contributors"]
    assert metadata.status_code == 200
    _assert_metadata_options(metadata.json())
    assert cover.status_code == 200
    assert cover.content == world.cover_content
    assert "no-store" in cover.headers["cache-control"]
    for response in (listed, detail, metadata):
        _assert_safe_catalogue_response(response.text)

    baseline = _snapshot(session, world)
    mutation_payload = payload("A2 forbidden Viewer rewrite")
    mutation_payload["author"] = "Forbidden Viewer Author"
    mutation_payload["contributors"] = [
        {"role_code": "AUTHOR", "name": "Forbidden Viewer Author"}
    ]
    attempts: tuple[tuple[str, Callable[[], Any]], ...] = (
        (
            "create book",
            lambda: client.post(
                catalogue_url,
                json=mutation_payload,
                headers=csrf(),
            ),
        ),
        (
            "update book and contributors",
            lambda: client.put(
                book_url,
                json=mutation_payload,
                headers=csrf(),
            ),
        ),
        (
            "delete book",
            lambda: client.request(
                "DELETE",
                book_url,
                json={"confirmation_title": "A2 protected catalogue book"},
                headers=csrf(),
            ),
        ),
        (
            "replace cover",
            lambda: client.put(
                cover_url,
                files={
                    "cover": (
                        "forbidden.png",
                        image_bytes(
                            size=(70, 100),
                            colour="yellow",
                            format="PNG",
                        ),
                        "image/png",
                    )
                },
                headers=csrf(),
            ),
        ),
        (
            "delete cover",
            lambda: client.delete(cover_url, headers=csrf()),
        ),
        (
            "ISBN lookup",
            lambda: client.get(
                f"{catalogue_url}/isbn-lookup",
                params={"isbn": "9780441478125"},
            ),
        ),
    )
    for label, attempt in attempts:
        response = attempt()
        assert response.status_code == 404, (label, response.text)
        assert _snapshot(session, world) == baseline, label

    unchanged = client.get(book_url)
    assert unchanged.status_code == 200
    assert unchanged.json()["title"] == "A2 protected catalogue book"
    assert client.get(cover_url).content == world.cover_content
