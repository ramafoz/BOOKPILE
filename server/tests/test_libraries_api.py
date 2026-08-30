from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import LibraryAuditEvent, LibraryMembership, User, UserSession
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.security.passwords import hash_password


CSRF = "library-api-test-csrf"
PASSWORD = "a valid library password"
PASSWORD_HASH = hash_password(PASSWORD)


def add_user(session: Session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash=PASSWORD_HASH,
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user


def authenticate(client: TestClient, session: Session, user: User) -> None:
    now = datetime.now(UTC)
    raw_token = f"library-api-{uuid4().hex}"
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_secret(raw_token),
            csrf_token_hash=hash_session_secret(CSRF),
            last_seen_at=now,
            expires_at=now + timedelta(days=7),
            absolute_expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, raw_token)
    client.cookies.set(settings.csrf_cookie_name, CSRF)


def csrf_headers() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF}


def test_create_list_invite_and_accept_viewer_membership(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "library_owner")
    viewer = add_user(session, "library_viewer")
    authenticate(client, session, owner)

    created = client.post(
        "/api/v1/libraries",
        json={"name": "  Shared   Home Library  "},
        headers=csrf_headers(),
    )

    assert created.status_code == 201
    library = created.json()
    assert library["name"] == "Shared Home Library"
    assert library["slug"] == "shared-home-library"
    assert library["role"] == "OWNER"
    assert library["viewer_scope"] is None
    assert library["can_view_map"] is True
    assert library["selected_reading_user_id"] == str(owner.id)

    listed = client.get("/api/v1/libraries")
    assert listed.status_code == 200
    assert [item["library_id"] for item in listed.json()] == [
        library["library_id"]
    ]

    invitation = client.post(
        f"/api/v1/libraries/{library['library_id']}/invitations",
        json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
        headers=csrf_headers(),
    )
    assert invitation.status_code == 201
    raw_invitation = invitation.json()["invitation_token"]

    authenticate(client, session, viewer)
    shared_url = (
        "http://localhost:5173/login?library-invite=" + raw_invitation
    )
    accepted = client.post(
        "/api/v1/library-invitations/accept",
        json={"invitation_token": shared_url},
        headers=csrf_headers(),
    )
    assert accepted.status_code == 200
    assert accepted.json()["role"] == "VIEWER"
    assert accepted.json()["viewer_scope"] == "CATALOG_ONLY"
    assert accepted.json()["can_view_map"] is False
    assert accepted.json()["selected_reading_user_id"] == str(owner.id)

    assert client.get(
        f"/api/v1/libraries/{library['library_id']}/catalogue"
    ).status_code == 200
    assert client.get(
        f"/api/v1/libraries/{library['library_id']}/members"
    ).status_code == 404
    assert client.post(
        f"/api/v1/libraries/{library['library_id']}/invitations",
        json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
        headers=csrf_headers(),
    ).status_code == 404

    third_user = add_user(session, "third_user")
    authenticate(client, session, third_user)
    reused = client.post(
        "/api/v1/library-invitations/accept",
        json={"invitation_token": raw_invitation},
        headers=csrf_headers(),
    )
    assert reused.status_code == 400

    memberships = list(session.scalars(select(LibraryMembership)))
    assert [(item.user_id, item.role) for item in memberships] == [
        (owner.id, "OWNER"),
        (viewer.id, "VIEWER"),
    ]
    assert [
        event.event_type
        for event in session.scalars(
            select(LibraryAuditEvent).order_by(LibraryAuditEvent.id)
        )
    ] == [
        "library_created",
        "library_invitation_created",
        "library_invitation_accepted",
    ]


def test_owner_invitation_requires_explicit_equal_power_acknowledgement(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "careful_owner")
    authenticate(client, session, owner)
    library_id = client.post(
        "/api/v1/libraries",
        json={"name": "Careful library"},
        headers=csrf_headers(),
    ).json()["library_id"]
    library_id = UUID(library_id)

    rejected = client.post(
        f"/api/v1/libraries/{library_id}/invitations",
        json={"role": "OWNER", "acknowledge_equal_owner_power": False},
        headers=csrf_headers(),
    )
    accepted = client.post(
        f"/api/v1/libraries/{library_id}/invitations",
        json={"role": "OWNER", "acknowledge_equal_owner_power": True},
        headers=csrf_headers(),
    )

    assert rejected.status_code == 422
    assert "authority" in rejected.json()["detail"]
    assert accepted.status_code == 201


def test_owner_manages_members_and_reading_perspectives_safely(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "managing_owner")
    candidate = add_user(session, "owner_candidate")
    viewer = add_user(session, "perspective_viewer")
    authenticate(client, session, owner)
    library_id = client.post(
        "/api/v1/libraries",
        json={"name": "Managed library"},
        headers=csrf_headers(),
    ).json()["library_id"]
    library_id = UUID(library_id)
    session.add_all(
        [
            LibraryMembership(
                library_id=library_id,
                user_id=candidate.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
                selected_reading_user_id=owner.id,
            ),
            LibraryMembership(
                library_id=library_id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_AND_MAP",
                selected_reading_user_id=owner.id,
            ),
        ]
    )
    session.commit()

    wrong_password = client.patch(
        f"/api/v1/libraries/{library_id}/members/{candidate.id}",
        json={
            "action": "PROMOTE_TO_OWNER",
            "current_password": "wrong password",
            "acknowledge_equal_owner_power": True,
        },
        headers=csrf_headers(),
    )
    missing_warning = client.patch(
        f"/api/v1/libraries/{library_id}/members/{candidate.id}",
        json={
            "action": "PROMOTE_TO_OWNER",
            "current_password": PASSWORD,
            "acknowledge_equal_owner_power": False,
        },
        headers=csrf_headers(),
    )
    promoted = client.patch(
        f"/api/v1/libraries/{library_id}/members/{candidate.id}",
        json={
            "action": "PROMOTE_TO_OWNER",
            "current_password": PASSWORD,
            "acknowledge_equal_owner_power": True,
        },
        headers=csrf_headers(),
    )

    assert wrong_password.status_code == 403
    assert missing_warning.status_code == 422
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "OWNER"
    assert promoted.json()["viewer_scope"] is None

    perspectives = client.get(
        f"/api/v1/libraries/{library_id}/reading-perspectives"
    )
    assert perspectives.status_code == 200
    assert {item["username"] for item in perspectives.json()} == {
        owner.username,
        candidate.username,
    }

    selected = client.put(
        f"/api/v1/libraries/{library_id}/reading-perspective",
        json={"user_id": str(candidate.id)},
        headers=csrf_headers(),
    )
    assert selected.status_code == 200
    assert next(
        item for item in selected.json() if item["selected"]
    )["username"] == candidate.username

    downgraded = client.patch(
        f"/api/v1/libraries/{library_id}/members/{candidate.id}",
        json={
            "action": "DOWNGRADE_TO_VIEWER",
            "viewer_scope": "CATALOG_ONLY",
            "current_password": PASSWORD,
        },
        headers=csrf_headers(),
    )
    assert downgraded.status_code == 200
    assert downgraded.json()["role"] == "VIEWER"

    after_downgrade = client.get(
        f"/api/v1/libraries/{library_id}/reading-perspectives"
    ).json()
    assert len(after_downgrade) == 1
    assert after_downgrade[0]["username"] == owner.username
    assert after_downgrade[0]["selected"] is True

    final_owner = client.patch(
        f"/api/v1/libraries/{library_id}/members/{owner.id}",
        json={"action": "REMOVE", "current_password": PASSWORD},
        headers=csrf_headers(),
    )
    assert final_owner.status_code == 409

    authenticate(client, session, viewer)
    viewer_perspectives = client.get(
        f"/api/v1/libraries/{library_id}/reading-perspectives"
    )
    assert viewer_perspectives.status_code == 200
    assert viewer_perspectives.json() == [
        {
            "user_id": str(owner.id),
            "username": owner.username,
            "selected": True,
            "writable": False,
        }
    ]


def test_catalog_only_viewer_cannot_receive_map_access(session: Session) -> None:
    from bookpile_server.repositories.libraries import LibraryRepository
    from bookpile_server.services.library_access import (
        LibraryAccessService,
        LibraryMapAccessDeniedError,
    )

    owner = add_user(session, "map_owner")
    viewer = add_user(session, "map_limited_viewer")
    from bookpile_server.models import Library

    library = Library(name="Sensitive map", slug="sensitive-map")
    session.add(library)
    session.flush()
    session.add_all(
        [
            LibraryMembership(
                library_id=library.id, user_id=owner.id, role="OWNER"
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
            ),
        ]
    )
    session.commit()
    access = LibraryAccessService(LibraryRepository(session))

    assert access.require_map(library_id=library.id, user_id=owner.id).can_view_map
    try:
        access.require_map(library_id=library.id, user_id=viewer.id)
    except LibraryMapAccessDeniedError:
        pass
    else:
        raise AssertionError("CATALOG_ONLY must never authorize map data")
