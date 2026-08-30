from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from ..models import AccountInvitation
from ..repositories.account_invitations import AccountInvitationRepository


ACCOUNT_INVITATION_LIFETIME = timedelta(days=7)


def hash_invitation_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


@dataclass(frozen=True)
class CreatedAccountInvitation:
    invitation_id: UUID
    raw_token: str
    expires_at: datetime


class AccountInvitationError(Exception):
    pass


class AccountInvitationService:
    def __init__(self, repository: AccountInvitationRepository) -> None:
        self._repository = repository

    def create(
        self, *, created_by_user_id: UUID | None = None
    ) -> CreatedAccountInvitation:
        now = datetime.now(UTC)
        raw_token = token_urlsafe(32)
        invitation = AccountInvitation(
            token_hash=hash_invitation_token(raw_token),
            created_by_user_id=created_by_user_id,
            created_at=now,
            expires_at=now + ACCOUNT_INVITATION_LIFETIME,
        )
        self._repository.add(invitation)
        self._repository.flush()
        self._repository.add_event(
            "account_invitation_created",
            user_id=created_by_user_id,
            details={"invitation_id": str(invitation.id)},
        )
        self._repository.commit()
        return CreatedAccountInvitation(
            invitation_id=invitation.id,
            raw_token=raw_token,
            expires_at=invitation.expires_at,
        )

    def revoke(self, invitation_id: UUID) -> None:
        invitation = self._repository.get(invitation_id)
        if invitation is None or invitation.consumed_at is not None:
            raise AccountInvitationError("Invitation cannot be revoked.")
        if invitation.revoked_at is None:
            invitation.revoked_at = datetime.now(UTC)
            self._repository.add_event(
                "account_invitation_revoked",
                user_id=invitation.created_by_user_id,
                details={"invitation_id": str(invitation.id)},
            )
            self._repository.commit()

    @staticmethod
    def is_usable(invitation: AccountInvitation, *, now: datetime) -> bool:
        return (
            invitation.revoked_at is None
            and invitation.consumed_at is None
            and now < utc_value(invitation.expires_at)
        )
