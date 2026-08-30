from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import AccountInvitation, SecurityEvent
from bookpile_server.repositories.account_invitations import (
    AccountInvitationRepository,
)
from bookpile_server.services.account_invitations import (
    AccountInvitationService,
    hash_invitation_token,
)


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
