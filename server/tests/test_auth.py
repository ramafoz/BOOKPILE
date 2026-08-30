from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import SecurityEvent, User, UserSession
from bookpile_server.security.passwords import (
    PasswordPolicyError,
    hash_password,
    verify_password,
)
from bookpile_server.services.auth import hash_session_secret


def add_active_user(session: Session, *, verified: bool = True) -> User:
    user = User(
        email="reader@example.test",
        username="reader_one",
        password_hash=hash_password("a valid password 🔐"),
        state="active",
        email_verified_at=datetime.now(UTC) if verified else None,
    )
    session.add(user)
    session.commit()
    return user


def test_password_policy_and_argon2id() -> None:
    password = "spaces and unicode á🔐"
    password_hash = hash_password(password)

    assert password_hash.startswith("$argon2id$")
    assert password not in password_hash
    assert verify_password(password_hash, password)
    assert not verify_password(password_hash, "wrong password")

    try:
        hash_password("too short")
    except PasswordPolicyError:
        pass
    else:
        raise AssertionError("short passwords must be rejected")


def test_login_creates_hashed_opaque_session_and_logout_revokes(
    client, session: Session
) -> None:
    user = add_active_user(session)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "READER_ONE",
            "password": "a valid password 🔐",
            "remember_me": False,
        },
    )

    assert response.status_code == 200
    assert response.json()["username"] == "reader_one"
    cookie = response.cookies.get("bookpile_session")
    csrf_token = response.cookies.get("bookpile_csrf")
    assert cookie
    assert csrf_token
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]
    set_cookies = response.headers.get_list("set-cookie")
    session_cookie = next(item for item in set_cookies if "bookpile_session=" in item)
    csrf_cookie = next(item for item in set_cookies if "bookpile_csrf=" in item)
    assert "Path=/api/v1" in session_cookie
    assert "HttpOnly" in session_cookie
    assert "Path=/;" in csrf_cookie
    assert "HttpOnly" not in csrf_cookie
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "same-origin"

    stored_session = session.scalar(select(UserSession))
    assert stored_session is not None
    assert stored_session.user_id == user.id
    assert stored_session.token_hash == hash_session_secret(cookie)
    assert cookie not in stored_session.token_hash
    assert len(stored_session.csrf_token_hash) == 64

    assert client.get("/api/v1/auth/me").json() == {
        "user_id": str(user.id),
        "username": "reader_one",
    }

    rejected_logout = client.post("/api/v1/auth/logout")
    assert rejected_logout.status_code == 403
    assert stored_session.revoked_at is None

    response = client.post(
        "/api/v1/auth/logout", headers={"X-CSRF-Token": csrf_token}
    )
    assert response.status_code == 204
    session.expire_all()
    stored_session = session.scalar(select(UserSession))
    assert stored_session is not None
    assert stored_session.revoked_at is not None
    assert [
        event.event_type
        for event in session.scalars(
            select(SecurityEvent).order_by(SecurityEvent.id)
        )
    ] == ["login_succeeded", "logout"]


def test_login_failures_are_generic(client, session: Session) -> None:
    add_active_user(session)

    wrong_password = client.post(
        "/api/v1/auth/login",
        json={"identifier": "reader_one", "password": "not the password"},
    )
    unknown_user = client.post(
        "/api/v1/auth/login",
        json={"identifier": "unknown", "password": "not the password"},
    )

    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json() == {
        "detail": "Invalid credentials"
    }


def test_unverified_user_cannot_login(client, session: Session) -> None:
    add_active_user(session, verified=False)

    response = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "reader@example.test",
            "password": "a valid password 🔐",
        },
    )

    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid credentials"}


def test_session_rotation_revokes_old_token(client, session: Session) -> None:
    add_active_user(session)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "reader_one",
            "password": "a valid password 🔐",
        },
    )
    old_cookie = login.cookies.get("bookpile_session")
    csrf_token = login.cookies.get("bookpile_csrf")
    assert old_cookie and csrf_token

    rotated = client.post(
        "/api/v1/auth/session/rotate",
        headers={"X-CSRF-Token": csrf_token},
    )
    assert rotated.status_code == 200
    new_cookie = rotated.cookies.get("bookpile_session")
    assert new_cookie and new_cookie != old_cookie

    sessions = list(
        session.scalars(select(UserSession).order_by(UserSession.created_at))
    )
    assert len(sessions) == 2
    assert sessions[0].revoked_at is not None
    assert sessions[1].revoked_at is None
    assert sessions[1].absolute_expires_at == sessions[0].absolute_expires_at
    assert client.get("/api/v1/auth/me").status_code == 200

    rotated_csrf = rotated.cookies.get("bookpile_csrf")
    assert rotated_csrf
    revoked = client.post(
        "/api/v1/auth/sessions/revoke-all",
        headers={"X-CSRF-Token": rotated_csrf},
    )
    assert revoked.status_code == 204
    assert client.get("/api/v1/auth/me").status_code == 401
    session.expire_all()
    assert all(
        item.revoked_at is not None
        for item in session.scalars(select(UserSession))
    )


def test_expired_session_is_rejected(client, session: Session) -> None:
    add_active_user(session)
    login = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "reader_one",
            "password": "a valid password 🔐",
        },
    )
    assert login.status_code == 200
    stored_session = session.scalar(select(UserSession))
    assert stored_session is not None
    stored_session.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    response = client.get("/api/v1/auth/me")
    assert response.status_code == 401
    assert response.json() == {"detail": "Authentication required"}
