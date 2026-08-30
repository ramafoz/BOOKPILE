from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from ..models import AccountInvitation, User
from ..repositories.account_invitations import AccountInvitationRepository
from ..security.identities import (
    IdentityValidationError,
    normalize_email,
    normalize_username,
)
from ..security.passwords import PasswordPolicyError, hash_password


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


class RegistrationValidationError(Exception):
    pass


class RegistrationConflictError(Exception):
    pass


@dataclass(frozen=True)
class RegisteredAccount:
    user_id: UUID
    email: str
    username: str
    state: str


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

    def register(
        self,
        *,
        raw_token: str,
        email: str,
        username: str,
        password: str,
        password_confirmation: str,
        ip_address: str | None,
    ) -> RegisteredAccount:
        if password != password_confirmation:
            raise RegistrationValidationError("Passwords do not match.")
        try:
            normalized_email = normalize_email(email)
            normalized_username = normalize_username(username)
            password_hash = hash_password(password)
        except (IdentityValidationError, PasswordPolicyError) as exc:
            raise RegistrationValidationError(str(exc)) from exc

        now = datetime.now(UTC)
        invitation = self._repository.get_by_token_hash_for_update(
            hash_invitation_token(raw_token)
        )
        if invitation is None or not self.is_usable(invitation, now=now):
            self._repository.rollback()
            raise AccountInvitationError("Account invitation is invalid or expired.")
        if self._repository.account_identity_exists(
            email=normalized_email, username=normalized_username
        ):
            self._repository.rollback()
            raise RegistrationConflictError("Account could not be created.")

        user = User(
            email=normalized_email,
            username=normalized_username,
            password_hash=password_hash,
            state="pending_verification",
        )
        self._repository.add_user(user)
        try:
            self._repository.flush()
            invitation.consumed_at = now
            invitation.consumed_by_user_id = user.id
            self._repository.add_event(
                "account_registered",
                user_id=user.id,
                ip_address=ip_address,
                details={"invitation_id": str(invitation.id)},
            )
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise RegistrationConflictError("Account could not be created.") from exc
        return RegisteredAccount(
            user_id=user.id,
            email=user.email,
            username=user.username,
            state=user.state,
        )

    @staticmethod
    def is_usable(invitation: AccountInvitation, *, now: datetime) -> bool:
        return (
            invitation.revoked_at is None
            and invitation.consumed_at is None
            and now < utc_value(invitation.expires_at)
        )
