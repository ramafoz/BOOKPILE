from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi.dependencies.models import Dependant
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bookpile_server.api.dependencies import get_library_access_service
from bookpile_server.config import get_settings
from bookpile_server.models import Book, Library, LibraryMembership, User, UserSession
from bookpile_server.repositories.libraries import LibraryRepository
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.services.library_access import LibraryAccessService
from test_catalogue_services import CSRF, authenticate, payload


PASSWORD = "valid a9 session password"
PUBLIC_MUTATION_ROUTES = {
    ("POST", "/api/v1/auth/register"),
    ("POST", "/api/v1/auth/verification/resend"),
    ("POST", "/api/v1/auth/verification/confirm"),
    ("POST", "/api/v1/auth/password-reset/request"),
    ("POST", "/api/v1/auth/password-reset/confirm"),
    ("POST", "/api/v1/auth/login"),
    ("POST", "/api/v1/auth/account-deletion/restore"),
}
AUTHENTICATED_READ_ONLY_POSTS = {
    (
        "POST",
        "/api/v1/libraries/{library_id}/physical-library/rearrangements/preview",
    )
}


def _add_user(session: Session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash=hash_password(PASSWORD),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user


def _dependency_names(route: APIRoute) -> set[str]:
    names: set[str] = set()

    def visit(dependency: Dependant) -> None:
        name = getattr(dependency.call, "__name__", None)
        if name is not None:
            names.add(name)
        for child in dependency.dependencies:
            visit(child)

    visit(route.dependant)
    return names


def _login(client: TestClient, user: User) -> tuple[str, str]:
    client.cookies.clear()
    response = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.username, "password": PASSWORD},
    )
    assert response.status_code == 200, response.text
    settings = get_settings()
    session_token = response.cookies.get(settings.session_cookie_name)
    csrf_token = response.cookies.get(settings.csrf_cookie_name)
    assert session_token is not None
    assert csrf_token is not None
    return session_token, csrf_token


def _use_session(client: TestClient, session_token: str, csrf_token: str) -> None:
    settings = get_settings()
    client.cookies.clear()
    client.cookies.set(settings.session_cookie_name, session_token)
    client.cookies.set(settings.csrf_cookie_name, csrf_token)


def test_every_authenticated_mutation_has_an_explicit_csrf_decision(
    client: TestClient,
) -> None:
    audited: set[tuple[str, str]] = set()
    for route in client.app.routes:
        if not isinstance(route, APIRoute):
            continue
        if not route.path.startswith("/api/v1"):
            continue
        if not route.methods.intersection({"POST", "PUT", "PATCH", "DELETE"}):
            continue
        unsafe_methods = route.methods.intersection(
            {"POST", "PUT", "PATCH", "DELETE"}
        )
        for method in unsafe_methods:
            endpoint = (method, route.path)
            dependencies = _dependency_names(route)
            authenticated = "get_current_auth" in dependencies
            csrf_protected = "require_csrf" in dependencies
            audited.add(endpoint)
            if endpoint in PUBLIC_MUTATION_ROUTES:
                assert not authenticated
                assert not csrf_protected
            elif endpoint in AUTHENTICATED_READ_ONLY_POSTS:
                assert authenticated
                assert not csrf_protected
            else:
                assert authenticated, (endpoint, route.name)
                assert csrf_protected, (endpoint, route.name)

    assert PUBLIC_MUTATION_ROUTES <= audited
    assert AUTHENTICATED_READ_ONLY_POSTS <= audited


def test_login_rotation_rejects_fixed_mixed_and_stale_session_secrets(
    client: TestClient,
    session: Session,
) -> None:
    user = _add_user(session, "a9_rotation_user")
    settings = get_settings()
    fixed_session = "attacker-selected-session"
    fixed_csrf = "attacker-selected-csrf"
    _use_session(client, fixed_session, fixed_csrf)

    old_session, old_csrf = _login(client, user)
    assert old_session != fixed_session
    assert old_csrf != fixed_csrf
    assert session.scalar(
        select(func.count())
        .select_from(UserSession)
        .where(UserSession.token_hash == hash_session_secret(fixed_session))
    ) == 0
    assert client.get("/api/v1/auth/me").status_code == 200

    _use_session(client, fixed_session, fixed_csrf)
    assert client.get("/api/v1/auth/me").status_code == 401
    _use_session(client, old_session, old_csrf)
    rotated = client.post(
        "/api/v1/auth/session/rotate",
        headers={"X-CSRF-Token": old_csrf},
    )
    assert rotated.status_code == 200, rotated.text
    new_session = rotated.cookies.get(settings.session_cookie_name)
    new_csrf = rotated.cookies.get(settings.csrf_cookie_name)
    assert new_session is not None and new_session != old_session
    assert new_csrf is not None and new_csrf != old_csrf

    for stale_csrf in (old_csrf, new_csrf):
        _use_session(client, old_session, stale_csrf)
        rejected = client.put(
            "/api/v1/auth/locale",
            json={"preferred_locale": "gl"},
            headers={"X-CSRF-Token": stale_csrf},
        )
        assert rejected.status_code == 401

    _use_session(client, new_session, new_csrf)
    mixed = client.put(
        "/api/v1/auth/locale",
        json={"preferred_locale": "gl"},
        headers={"X-CSRF-Token": old_csrf},
    )
    assert mixed.status_code == 403
    accepted = client.put(
        "/api/v1/auth/locale",
        json={"preferred_locale": "gl"},
        headers={"X-CSRF-Token": new_csrf},
    )
    assert accepted.status_code == 200
    session.expire_all()
    stored = list(session.scalars(select(UserSession).order_by(UserSession.created_at)))
    assert len(stored) == 2
    assert stored[0].revoked_at is not None
    assert stored[1].revoked_at is None


def test_revoke_all_invalidates_every_established_session_and_csrf_pair(
    client: TestClient,
    session: Session,
) -> None:
    user = _add_user(session, "a9_revoke_all_user")
    first_session, first_csrf = _login(client, user)
    second_session, second_csrf = _login(client, user)

    _use_session(client, first_session, first_csrf)
    response = client.post(
        "/api/v1/auth/sessions/revoke-all",
        headers={"X-CSRF-Token": first_csrf},
    )
    assert response.status_code == 204

    for stale_session, stale_csrf in (
        (first_session, first_csrf),
        (second_session, second_csrf),
    ):
        _use_session(client, stale_session, stale_csrf)
        assert client.get("/api/v1/auth/me").status_code == 401
        mutation = client.put(
            "/api/v1/auth/locale",
            json={"preferred_locale": "gl"},
            headers={"X-CSRF-Token": stale_csrf},
        )
        assert mutation.status_code == 401

    session.expire_all()
    sessions = list(session.scalars(select(UserSession)))
    assert len(sessions) == 2
    assert all(item.revoked_at is not None for item in sessions)
    assert session.get(User, user.id).preferred_locale == "en"


def test_in_flight_request_rechecks_membership_after_authentication(
    client: TestClient,
    session: Session,
) -> None:
    removed_owner = _add_user(session, "a9_removed_owner")
    surviving_owner = _add_user(session, "a9_surviving_owner")
    library = Library(
        name="A9 temporal access",
        slug=f"a9-temporal-{uuid4().hex}",
        created_by_user_id=removed_owner.id,
    )
    session.add(library)
    session.flush()
    session.add_all(
        (
            LibraryMembership(
                library_id=library.id,
                user_id=removed_owner.id,
                role="OWNER",
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=surviving_owner.id,
                role="OWNER",
            ),
        )
    )
    session.commit()
    authenticate(client, session, removed_owner)

    class RemoveBeforeAuthorization:
        def __init__(self) -> None:
            self.real = LibraryAccessService(LibraryRepository(session))
            self.removed = False

        def require_owner(self, *, library_id: UUID, user_id: UUID) -> Any:
            assert not self.removed
            membership = session.scalar(
                select(LibraryMembership).where(
                    LibraryMembership.library_id == library_id,
                    LibraryMembership.user_id == user_id,
                )
            )
            assert membership is not None
            session.delete(membership)
            session.commit()
            self.removed = True
            return self.real.require_owner(library_id=library_id, user_id=user_id)

    temporal_access = RemoveBeforeAuthorization()
    client.app.dependency_overrides[get_library_access_service] = lambda: temporal_access
    endpoint = f"/api/v1/libraries/{library.id}/catalogue"
    rejected = client.post(
        endpoint,
        json=payload("A9 must never be created"),
        headers={"X-CSRF-Token": CSRF},
    )
    assert temporal_access.removed is True
    assert rejected.status_code == 404
    assert session.scalar(select(func.count()).select_from(Book)) == 0
    client.app.dependency_overrides.pop(get_library_access_service)
    assert client.get(endpoint).status_code == 404
    assert client.get("/api/v1/auth/me").status_code == 200

    client.cookies.clear()
    authenticate(client, session, surviving_owner)
    assert client.get(endpoint).status_code == 200
