from datetime import UTC, datetime

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
    assert cookie
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "SameSite=lax" in response.headers["set-cookie"]

    stored_session = session.scalar(select(UserSession))
    assert stored_session is not None
    assert stored_session.user_id == user.id
    assert stored_session.token_hash == hash_session_secret(cookie)
    assert cookie not in stored_session.token_hash
    assert len(stored_session.csrf_token_hash) == 64

    response = client.post("/api/v1/auth/logout")
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
