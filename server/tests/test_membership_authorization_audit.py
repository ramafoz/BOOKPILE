from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import (
    Library,
    LibraryAuditEvent,
    LibraryInvitation,
    LibraryMembership,
)
from test_libraries_api import (
    PASSWORD,
    add_user,
    authenticate,
    csrf_headers,
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
        "libraries": rows(Library),
        "memberships": rows(LibraryMembership),
        "invitations": rows(LibraryInvitation),
        "audit": rows(LibraryAuditEvent),
    }


def test_invitation_and_membership_authorization_lifecycle(
    client: TestClient,
    session: Session,
) -> None:
    first_owner = add_user(session, "a5_first_owner")
    second_owner = add_user(session, "a5_second_owner")
    catalogue_viewer = add_user(session, "a5_catalogue_viewer")
    map_viewer = add_user(session, "a5_map_viewer")
    invited_user = add_user(session, "a5_invited_user")
    library = Library(
        name="A5 membership library",
        slug="a5-membership-library",
        created_by_user_id=first_owner.id,
    )
    session.add(library)
    session.flush()
    session.add_all(
        (
            LibraryMembership(
                library_id=library.id,
                user_id=first_owner.id,
                role="OWNER",
                selected_reading_user_id=first_owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=second_owner.id,
                role="OWNER",
                selected_reading_user_id=second_owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=catalogue_viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
                selected_reading_user_id=first_owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=map_viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_AND_MAP",
                selected_reading_user_id=first_owner.id,
            ),
        )
    )
    session.commit()
    root = f"/api/v1/libraries/{library.id}"

    _authenticate(client, session, first_owner)
    settings = get_settings()
    original_owner_session_cookie = client.cookies.get(
        settings.session_cookie_name
    )
    original_owner_csrf_cookie = client.cookies.get(settings.csrf_cookie_name)
    assert original_owner_session_cookie is not None
    assert original_owner_csrf_cookie is not None
    members = client.get(f"{root}/members")
    assert members.status_code == 200
    assert {item["user_id"] for item in members.json()} == {
        str(first_owner.id),
        str(second_owner.id),
        str(catalogue_viewer.id),
        str(map_viewer.id),
    }
    created = client.post(
        f"{root}/invitations",
        json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
        headers=csrf_headers(),
    )
    assert created.status_code == 201, created.text
    invitation_id = created.json()["invitation_id"]
    invitation_token = created.json()["invitation_token"]

    for viewer in (catalogue_viewer, map_viewer):
        _authenticate(client, session, viewer)
        assert client.get(f"{root}/members").status_code == 404
        summary = client.get(f"{root}/member-summary")
        assert summary.status_code == 200
        assert {item["user_id"] for item in summary.json()} == {
            str(first_owner.id),
            str(second_owner.id),
            str(catalogue_viewer.id),
            str(map_viewer.id),
        }
        baseline = _snapshot(session)
        forbidden: tuple[tuple[str, Callable[[], Any]], ...] = (
            (
                "create invitation",
                lambda: client.post(
                    f"{root}/invitations",
                    json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
                    headers=csrf_headers(),
                ),
            ),
            (
                "revoke invitation",
                lambda: client.delete(
                    f"{root}/invitations/{invitation_id}",
                    headers=csrf_headers(),
                ),
            ),
            (
                "change scope",
                lambda: client.patch(
                    f"{root}/members/{catalogue_viewer.id}",
                    json={
                        "action": "CHANGE_VIEWER_SCOPE",
                        "viewer_scope": "CATALOG_AND_MAP",
                        "current_password": PASSWORD,
                    },
                    headers=csrf_headers(),
                ),
            ),
            (
                "promote member",
                lambda: client.patch(
                    f"{root}/members/{catalogue_viewer.id}",
                    json={
                        "action": "PROMOTE_TO_OWNER",
                        "current_password": PASSWORD,
                        "acknowledge_equal_owner_power": True,
                    },
                    headers=csrf_headers(),
                ),
            ),
            (
                "remove member",
                lambda: client.patch(
                    f"{root}/members/{catalogue_viewer.id}",
                    json={"action": "REMOVE", "current_password": PASSWORD},
                    headers=csrf_headers(),
                ),
            ),
        )
        for label, attempt in forbidden:
            response = attempt()
            assert response.status_code == 404, (label, response.text)
            assert _snapshot(session) == baseline, label

    _authenticate(client, session, first_owner)
    changed_scope = client.patch(
        f"{root}/members/{catalogue_viewer.id}",
        json={
            "action": "CHANGE_VIEWER_SCOPE",
            "viewer_scope": "CATALOG_AND_MAP",
            "current_password": PASSWORD,
        },
        headers=csrf_headers(),
    )
    assert changed_scope.status_code == 200
    assert changed_scope.json()["viewer_scope"] == "CATALOG_AND_MAP"
    promoted = client.patch(
        f"{root}/members/{catalogue_viewer.id}",
        json={
            "action": "PROMOTE_TO_OWNER",
            "current_password": PASSWORD,
            "acknowledge_equal_owner_power": True,
        },
        headers=csrf_headers(),
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "OWNER"
    downgraded = client.patch(
        f"{root}/members/{catalogue_viewer.id}",
        json={
            "action": "DOWNGRADE_TO_VIEWER",
            "viewer_scope": "CATALOG_ONLY",
            "current_password": PASSWORD,
        },
        headers=csrf_headers(),
    )
    assert downgraded.status_code == 200
    assert downgraded.json()["role"] == "VIEWER"
    removed = client.patch(
        f"{root}/members/{catalogue_viewer.id}",
        json={"action": "REMOVE", "current_password": PASSWORD},
        headers=csrf_headers(),
    )
    assert removed.status_code == 200
    assert removed.json() is None

    _authenticate(client, session, second_owner)
    revoked = client.delete(
        f"{root}/invitations/{invitation_id}",
        headers=csrf_headers(),
    )
    assert revoked.status_code == 204
    before_stale_invitation = _snapshot(session)
    _authenticate(client, session, invited_user)
    stale_acceptance = client.post(
        "/api/v1/library-invitations/accept",
        json={"invitation_token": invitation_token},
        headers=csrf_headers(),
    )
    assert stale_acceptance.status_code == 400
    assert _snapshot(session) == before_stale_invitation

    _authenticate(client, session, second_owner)
    remove_first_owner = client.patch(
        f"{root}/members/{first_owner.id}",
        json={"action": "REMOVE", "current_password": PASSWORD},
        headers=csrf_headers(),
    )
    assert remove_first_owner.status_code == 200

    client.cookies.clear()
    client.cookies.set(
        settings.session_cookie_name,
        original_owner_session_cookie,
    )
    client.cookies.set(settings.csrf_cookie_name, original_owner_csrf_cookie)
    stale_session_baseline = _snapshot(session)
    stale_owner_request = client.post(
        f"{root}/invitations",
        json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
        headers=csrf_headers(),
    )
    assert stale_owner_request.status_code == 404
    assert _snapshot(session) == stale_session_baseline

    _authenticate(client, session, second_owner)
    final_owner_baseline = _snapshot(session)
    final_owner = client.patch(
        f"{root}/members/{second_owner.id}",
        json={"action": "REMOVE", "current_password": PASSWORD},
        headers=csrf_headers(),
    )
    assert final_owner.status_code == 409
    assert _snapshot(session) == final_owner_baseline
