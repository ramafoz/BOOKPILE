from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import AccountInvitation, SecurityEvent, User
from bookpile_server.repositories.account_invitations import (
    AccountInvitationRepository,
)
from bookpile_server.services.account_invitations import (
    AccountInvitationService,
    hash_invitation_token,
)
from bookpile_server.security.passwords import verify_password


def test_account_invitation_stores_only_token_hash(session: Session) -> None:
    service = AccountInvitationService(AccountInvitationRepository(session))

    result = service.create()

    invitation = session.scalar(select(AccountInvitation))
    assert invitation is not None
    assert invitation.id == result.invitation_id
    assert invitation.token_hash == hash_invitation_token(result.raw_token)
    assert result.raw_token not in invitation.token_hash
    assert invitation.created_by_user_id is None
    event = session.scalar(select(SecurityEvent))
    assert event is not None
    assert event.event_type == "account_invitation_created"
    assert event.details["invitation_id"] == str(invitation.id)


def test_account_invitation_can_be_revoked(session: Session) -> None:
    service = AccountInvitationService(AccountInvitationRepository(session))
    result = service.create()

    service.revoke(result.invitation_id)
    invitation = session.get(AccountInvitation, result.invitation_id)
    assert invitation is not None
    assert invitation.revoked_at is not None
    assert not service.is_usable(invitation, now=datetime.now(UTC))


def test_expired_account_invitation_is_not_usable(session: Session) -> None:
    service = AccountInvitationService(AccountInvitationRepository(session))
    result = service.create()
    invitation = session.get(AccountInvitation, result.invitation_id)
    assert invitation is not None
    invitation.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()

    assert not service.is_usable(invitation, now=datetime.now(UTC))


def registration_payload(token: str, **changes: str) -> dict[str, str]:
    payload = {
        "invitation_token": token,
        "email": "new.reader@example.com",
        "username": "new_reader",
        "password": "a valid registration password 🔐",
        "password_confirmation": "a valid registration password 🔐",
    }
    payload.update(changes)
    return payload


def test_registration_atomically_consumes_invitation(client, session: Session) -> None:
    service = AccountInvitationService(AccountInvitationRepository(session))
    invitation_result = service.create()

    response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(invitation_result.raw_token),
    )

    assert response.status_code == 201
    assert response.json()["username"] == "new_reader"
    assert response.json()["state"] == "pending_verification"
    assert "bookpile_session" not in response.cookies
    user = session.scalar(select(User).where(User.username == "new_reader"))
    assert user is not None
    assert user.email == "new.reader@example.com"
    assert verify_password(user.password_hash, "a valid registration password 🔐")
    invitation = session.get(AccountInvitation, invitation_result.invitation_id)
    assert invitation is not None
    assert invitation.consumed_by_user_id == user.id
    assert invitation.consumed_at is not None

    reused = client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            invitation_result.raw_token,
            email="second.reader@example.com",
            username="second_reader",
        ),
    )
    assert reused.status_code == 400
    assert session.scalar(select(User).where(User.username == "second_reader")) is None

    # Registration does not bypass the future email-verification phase.
    login = client.post(
        "/api/v1/auth/login",
        json={
            "identifier": "new_reader",
            "password": "a valid registration password 🔐",
        },
    )
    assert login.status_code == 401


def test_invalid_registration_does_not_consume_invitation(client, session: Session) -> None:
    service = AccountInvitationService(AccountInvitationRepository(session))
    invitation_result = service.create()

    mismatch = client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            invitation_result.raw_token,
            password_confirmation="different password",
        ),
    )
    assert mismatch.status_code == 422

    reserved = client.post(
        "/api/v1/auth/register",
        json=registration_payload(invitation_result.raw_token, username="RAMAFOZ"),
    )
    assert reserved.status_code == 422
    invitation = session.get(AccountInvitation, invitation_result.invitation_id)
    assert invitation is not None
    assert invitation.consumed_at is None
    assert session.scalar(select(User)) is None


def test_duplicate_identity_is_generic_and_preserves_invitation(
    client, session: Session
) -> None:
    session.add(
        User(
            email="existing@example.com",
            username="existing_reader",
            password_hash="placeholder",
            state="pending_verification",
        )
    )
    session.commit()
    service = AccountInvitationService(AccountInvitationRepository(session))
    invitation_result = service.create()

    response = client.post(
        "/api/v1/auth/register",
        json=registration_payload(
            invitation_result.raw_token,
            email="another@example.com",
            username="EXISTING_READER",
        ),
    )

    assert response.status_code == 409
    assert response.json() == {"detail": "Account could not be created"}
    invitation = session.get(AccountInvitation, invitation_result.invitation_id)
    assert invitation is not None
    assert invitation.consumed_at is None


def test_expired_or_revoked_invitation_cannot_register(
    client, session: Session
) -> None:
    service = AccountInvitationService(AccountInvitationRepository(session))
    expired = service.create()
    expired_record = session.get(AccountInvitation, expired.invitation_id)
    assert expired_record is not None
    expired_record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    session.commit()
    revoked = service.create()
    service.revoke(revoked.invitation_id)

    for number, token in enumerate((expired.raw_token, revoked.raw_token), start=1):
        response = client.post(
            "/api/v1/auth/register",
            json=registration_payload(
                token,
                email=f"blocked{number}@example.com",
                username=f"blocked_{number}",
            ),
        )
        assert response.status_code == 400
        assert response.json() == {
            "detail": "Account invitation is invalid or expired"
        }

    assert session.scalar(select(User)) is None
