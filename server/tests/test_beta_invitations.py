from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.models import (
    AccountInvitation,
    BetaInvitationProgress,
    User,
    UserSession,
)
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.account_invitations import hash_invitation_token
from bookpile_server.services.auth import hash_session_secret


PASSWORD = "a valid registration password 🔐"
CSRF = "beta-invitation-csrf"


def authenticated_user(client: TestClient, session: Session) -> User:
    user = User(
        email="active-inviter@example.test",
        username="active_inviter",
        password_hash=hash_password(PASSWORD),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    raw_session = f"beta-{uuid4().hex}"
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_secret(raw_session),
            csrf_token_hash=hash_session_secret(CSRF),
            last_seen_at=now,
            expires_at=now + timedelta(days=7),
            absolute_expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, raw_session)
    client.cookies.set(settings.csrf_cookie_name, CSRF)
    return user


def test_three_distinct_active_days_earn_one_single_use_account_invitation(
    client: TestClient, session: Session
) -> None:
    user = authenticated_user(client, session)

    first = client.get("/api/v1/account/beta-invitations")
    assert first.status_code == 200
    assert first.json()["active_day_count"] == 1
    assert client.get("/api/v1/account/beta-invitations").json()["active_day_count"] == 1

    progress = session.get(BetaInvitationProgress, user.id)
    assert progress is not None
    progress.last_active_on = datetime.now(UTC).date() - timedelta(days=1)
    session.commit()
    assert client.get("/api/v1/account/beta-invitations").json()["active_day_count"] == 2

    progress.last_active_on = datetime.now(UTC).date() - timedelta(days=1)
    session.commit()
    earned = client.get("/api/v1/account/beta-invitations").json()
    assert earned["active_day_count"] == 0
    assert earned["available_credits"] == 1

    created = client.post(
        "/api/v1/account/beta-invitations",
        headers={"X-CSRF-Token": CSRF},
    )
    assert created.status_code == 201
    raw_token = created.json()["invitation_token"]
    invitation = session.query(AccountInvitation).filter_by(
        created_by_user_id=user.id
    ).one()
    assert invitation.token_hash == hash_invitation_token(raw_token)
    assert invitation.token_hash != raw_token
    assert client.post(
        "/api/v1/account/beta-invitations",
        headers={"X-CSRF-Token": CSRF},
    ).status_code == 409

    registered = client.post(
        "/api/v1/auth/register",
        json={
            "invitation_token": raw_token,
            "email": "invited.friend@example.com",
            "username": "invited_friend",
            "password": PASSWORD,
            "password_confirmation": PASSWORD,
        },
    )
    assert registered.status_code == 201, registered.text
    session.refresh(invitation)
    assert invitation.consumed_at is not None
