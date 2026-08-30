from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse

from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import AccountActionToken, User, UserSession
from bookpile_server.security.passwords import hash_password, verify_password
from bookpile_server.services.account_actions import hash_action_token


OLD_PASSWORD = "the original valid password"
NEW_PASSWORD = "the replacement valid password"


def add_active_user(session: Session) -> User:
    now = datetime.now(UTC)
    user = User(
        email="active.reader@example.com",
        username="active_reader",
        password_hash=hash_password(OLD_PASSWORD),
        state="active",
        email_verified_at=now,
    )
    session.add(user)
    session.commit()
    return user


def token_from_email(text: str) -> str:
    url = next(line for line in text.splitlines() if "?token=" in line)
    return parse_qs(urlparse(url).query)["token"][0]


def test_password_reset_is_generic_changes_hash_and_revokes_sessions(
    client, session: Session, email_sender
) -> None:
    user = add_active_user(session)
    login = client.post(
        "/api/v1/auth/login",
        json={"identifier": user.username, "password": OLD_PASSWORD},
    )
    assert login.status_code == 200

    requested = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "ACTIVE.READER@example.com"},
    )
    unknown = client.post(
        "/api/v1/auth/password-reset/request",
        json={"email": "unknown@example.com"},
    )
    assert requested.status_code == unknown.status_code == 202
    assert requested.content == unknown.content
    assert len(email_sender.emails) == 1
    assert email_sender.emails[0].subject == "Reset your BOOKPILE password"
    raw_token = token_from_email(email_sender.emails[0].text)

    reset = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": NEW_PASSWORD,
            "password_confirmation": NEW_PASSWORD,
        },
    )
    assert reset.status_code == 204
    session.expire_all()
    user = session.get(User, user.id)
    assert user is not None
    assert verify_password(user.password_hash, NEW_PASSWORD)
    assert not verify_password(user.password_hash, OLD_PASSWORD)
    assert all(
        item.revoked_at is not None
        for item in session.scalars(select(UserSession))
    )
    assert client.get("/api/v1/auth/me").status_code == 401

    old_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "active_reader", "password": OLD_PASSWORD},
    )
    new_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": "active_reader", "password": NEW_PASSWORD},
    )
    assert old_login.status_code == 401
    assert new_login.status_code == 200

    reused = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": "another valid replacement",
            "password_confirmation": "another valid replacement",
        },
    )
    assert reused.status_code == 400


def test_invalid_password_reset_does_not_consume_token(
    client, session: Session, email_sender
) -> None:
    user = add_active_user(session)
    client.post(
        "/api/v1/auth/password-reset/request", json={"email": user.email}
    )
    raw_token = token_from_email(email_sender.emails[0].text)

    mismatch = client.post(
        "/api/v1/auth/password-reset/confirm",
        json={
            "token": raw_token,
            "password": NEW_PASSWORD,
            "password_confirmation": "does not match",
        },
    )
    assert mismatch.status_code == 422
    token = session.scalar(
        select(AccountActionToken).where(
            AccountActionToken.token_hash == hash_action_token(raw_token)
        )
    )
    assert token is not None
    assert token.consumed_at is None


def test_expired_action_tokens_are_rejected(client, session: Session) -> None:
    user = add_active_user(session)
    for purpose, endpoint, payload in (
        (
            "email_verification",
            "/api/v1/auth/verification/confirm",
            {"token": "v" * 43},
        ),
        (
            "password_reset",
            "/api/v1/auth/password-reset/confirm",
            {
                "token": "r" * 43,
                "password": NEW_PASSWORD,
                "password_confirmation": NEW_PASSWORD,
            },
        ),
    ):
        raw_token = payload["token"]
        session.add(
            AccountActionToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_action_token(raw_token),
                expires_at=datetime.now(UTC) - timedelta(seconds=1),
            )
        )
        session.commit()
        response = client.post(endpoint, json=payload)
        assert response.status_code == 400
