from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server import main
from bookpile_server.api import dependencies
from bookpile_server.config import Settings
from bookpile_server.database import get_session
from bookpile_server.models import (
    Library,
    LibraryMembership,
    RateLimitBucket,
    SecurityEvent,
    User,
    UserSession,
)
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.services.rate_limits import (
    RateLimitDecisionUnavailableError,
    RateLimiter,
)


CSRF = "mutation-limit-csrf"


def limit_settings(
    *,
    user_mode: str = "off",
    library_mode: str = "off",
    user_attempts: int = 1,
    library_attempts: int = 1,
) -> Settings:
    return Settings(
        environment="test",
        deployment_revision="git-mutation-limits",
        rate_limit_key_secret="mutation-limit-secret",
        mutation_user_limit_mode=user_mode,
        mutation_library_limit_mode=library_mode,
    ).model_copy(
        update={
            "mutation_attempts_per_user_per_15_minutes": user_attempts,
            "mutation_attempts_per_library_per_15_minutes": library_attempts,
        }
    )


def limited_client(monkeypatch, session: Session, settings: Settings) -> TestClient:
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    monkeypatch.setattr(dependencies, "get_settings", lambda: settings)
    app = main.create_app()

    def override_session():
        yield session

    app.dependency_overrides[get_session] = override_session
    return TestClient(app)


def add_user(session: Session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash=hash_password("valid mutation password"),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user


def authenticate(client: TestClient, session: Session, user: User) -> None:
    token = f"mutation-{uuid4().hex}"
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
    client.cookies.set("bookpile_session", token)
    client.cookies.set("bookpile_csrf", CSRF)


def add_library(session: Session, *members: User) -> Library:
    library = Library(name=f"Mutation {uuid4().hex[:6]}", slug=uuid4().hex)
    session.add(library)
    session.flush()
    session.add_all(
        LibraryMembership(library_id=library.id, user_id=user.id, role="OWNER")
        for user in members
    )
    session.commit()
    return library


def csrf() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF}


def buckets(session: Session, scope: str) -> list[RateLimitBucket]:
    session.expire_all()
    return list(
        session.scalars(
            select(RateLimitBucket).where(RateLimitBucket.scope == scope)
        )
    )


def test_authenticated_mutations_are_limited_per_user(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings(user_mode="enforce")
    user = add_user(session, "mutation_user")
    with limited_client(monkeypatch, session, settings) as client:
        authenticate(client, session, user)
        first = client.put(
            "/api/v1/auth/locale", json={"preferred_locale": "es"}, headers=csrf()
        )
        blocked = client.put(
            "/api/v1/auth/locale", json={"preferred_locale": "gl"}, headers=csrf()
        )

    assert first.status_code == 200
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many requests. Try again later."}
    assert int(blocked.headers["retry-after"]) > 0
    user_buckets = buckets(session, "mutation_user")
    assert len(user_buckets) == 1
    assert user_buckets[0].attempt_count == 2
    assert str(user.id) not in user_buckets[0].key_hash
    events = list(
        session.scalars(
            select(SecurityEvent).where(
                SecurityEvent.event_type == "rate_limit_blocked",
                SecurityEvent.details["scope"].as_string() == "mutation_user",
            )
        )
    )
    assert len(events) == 1
    assert events[0].ip_address is None
    assert events[0].details == {
        "scope": "mutation_user",
        "mode": "enforce",
        "deployment_revision": settings.deployment_revision,
    }


def test_library_limit_counts_only_active_members(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings(library_mode="enforce")
    first_owner = add_user(session, "mutation_owner")
    second_owner = add_user(session, "mutation_coowner")
    outsider = add_user(session, "mutation_outsider")
    library = add_library(session, first_owner, second_owner)

    with limited_client(monkeypatch, session, settings) as client:
        authenticate(client, session, outsider)
        inaccessible = client.post(
            f"/api/v1/libraries/{library.id}/invitations",
            json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
            headers=csrf(),
        )
        assert inaccessible.status_code == 404
        assert buckets(session, "mutation_library") == []

        authenticate(client, session, first_owner)
        first = client.post(
            f"/api/v1/libraries/{library.id}/invitations",
            json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
            headers=csrf(),
        )
        authenticate(client, session, second_owner)
        blocked = client.post(
            f"/api/v1/libraries/{library.id}/invitations",
            json={"role": "VIEWER", "viewer_scope": "CATALOG_ONLY"},
            headers=csrf(),
        )

    assert first.status_code == 201
    assert blocked.status_code == 429
    library_buckets = buckets(session, "mutation_library")
    assert len(library_buckets) == 1
    assert library_buckets[0].attempt_count == 2
    assert str(library.id) not in library_buckets[0].key_hash


def test_users_have_independent_buckets_behind_one_client(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings(user_mode="enforce")
    first_user = add_user(session, "mutation_first")
    second_user = add_user(session, "mutation_second")

    with limited_client(monkeypatch, session, settings) as client:
        authenticate(client, session, first_user)
        assert client.put(
            "/api/v1/auth/locale", json={"preferred_locale": "es"}, headers=csrf()
        ).status_code == 200
        authenticate(client, session, second_user)
        assert client.put(
            "/api/v1/auth/locale", json={"preferred_locale": "es"}, headers=csrf()
        ).status_code == 200

    user_buckets = buckets(session, "mutation_user")
    assert len(user_buckets) == 2
    assert {item.attempt_count for item in user_buckets} == {1}


def test_anonymous_mutation_is_not_counted(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings(user_mode="enforce")
    with limited_client(monkeypatch, session, settings) as client:
        response = client.post(
            "/api/v1/auth/login",
            json={
                "identifier": "missing",
                "password": "not-a-real-password",
                "remember_me": False,
            },
        )

    assert response.status_code == 401
    assert buckets(session, "mutation_user") == []


def test_mutation_limit_decision_failure_is_generic_503(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings(user_mode="enforce")
    user = add_user(session, "mutation_failure")

    def unavailable(*_args, **_kwargs):
        raise RateLimitDecisionUnavailableError

    monkeypatch.setattr(RateLimiter, "apply", unavailable)
    with limited_client(monkeypatch, session, settings) as client:
        authenticate(client, session, user)
        response = client.put(
            "/api/v1/auth/locale", json={"preferred_locale": "es"}, headers=csrf()
        )

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Request limiting is temporarily unavailable."
    }
