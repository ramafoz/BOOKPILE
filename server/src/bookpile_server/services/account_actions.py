from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import UUID

from ..config import Settings
from ..email_delivery import EmailSender, OutgoingEmail
from ..models import AccountActionToken, User
from ..repositories.account_actions import AccountActionRepository
from ..security.identities import IdentityValidationError, normalize_email
from ..security.passwords import PasswordPolicyError, hash_password


EMAIL_VERIFICATION_LIFETIME = timedelta(hours=24)
PASSWORD_RESET_LIFETIME = timedelta(minutes=30)


def hash_action_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class InvalidAccountActionTokenError(Exception):
    pass


class PasswordResetValidationError(Exception):
    pass


class AccountActionService:
    def __init__(
        self,
        repository: AccountActionRepository,
        email_sender: EmailSender,
        settings: Settings,
    ) -> None:
        self._repository = repository
        self._email_sender = email_sender
        self._settings = settings

    def send_verification_for_user(
        self, user_id: UUID, *, ip_address: str | None = None
    ) -> bool:
        user = self._repository.get_user(user_id)
        if user is None or user.state != "pending_verification":
            return False
        raw_token = self._issue_token(
            user=user,
            purpose="email_verification",
            lifetime=EMAIL_VERIFICATION_LIFETIME,
            event_type="email_verification_requested",
            ip_address=ip_address,
        )
        query = urlencode({"token": raw_token})
        self._email_sender.send(
            OutgoingEmail(
                recipient=user.email,
                subject="Verify your BOOKPILE email",
                text=(
                    "Verify your BOOKPILE account using this link:\n\n"
                    f"{self._settings.public_base_url.rstrip('/')}/verify-email?{query}\n\n"
                    "This link expires in 24 hours."
                ),
            )
        )
        return True

    def resend_verification(
        self, email: str, *, ip_address: str | None = None
    ) -> None:
        try:
            normalized = normalize_email(email)
        except IdentityValidationError:
            return
        user = self._repository.find_user_by_email(normalized)
        if user is not None:
            self.send_verification_for_user(user.id, ip_address=ip_address)

    def verify_email(self, raw_token: str, *, ip_address: str | None = None) -> None:
        now = datetime.now(UTC)
        token = self._repository.get_token_for_update(
            token_hash=hash_action_token(raw_token),
            purpose="email_verification",
        )
        if token is None or not self._is_usable(token, now=now):
            self._repository.rollback()
            raise InvalidAccountActionTokenError
        user = token.user
        if user.state != "pending_verification":
            self._repository.rollback()
            raise InvalidAccountActionTokenError
        token.consumed_at = now
        user.email_verified_at = now
        user.state = "active"
        user.updated_at = now
        self._repository.revoke_open_tokens(
            user_id=user.id,
            purpose="email_verification",
            now=now,
        )
        self._repository.add_event(
            "email_verified", user_id=user.id, ip_address=ip_address
        )
        self._repository.commit()

    def request_password_reset(
        self, email: str, *, ip_address: str | None = None
    ) -> None:
        try:
            normalized = normalize_email(email)
        except IdentityValidationError:
            return
        user = self._repository.find_user_by_email(normalized)
        if user is None or user.state != "active":
            return
        raw_token = self._issue_token(
            user=user,
            purpose="password_reset",
            lifetime=PASSWORD_RESET_LIFETIME,
            event_type="password_reset_requested",
            ip_address=ip_address,
        )
        query = urlencode({"token": raw_token})
        self._email_sender.send(
            OutgoingEmail(
                recipient=user.email,
                subject="Reset your BOOKPILE password",
                text=(
                    "Reset your BOOKPILE password using this link:\n\n"
                    f"{self._settings.public_base_url.rstrip('/')}/reset-password?{query}\n\n"
                    "This link expires in 30 minutes. If you did not request it, "
                    "you can ignore this email."
                ),
            )
        )

    def reset_password(
        self,
        *,
        raw_token: str,
        password: str,
        password_confirmation: str,
        ip_address: str | None = None,
    ) -> None:
        if password != password_confirmation:
            raise PasswordResetValidationError("Passwords do not match.")
        try:
            password_hash = hash_password(password)
        except PasswordPolicyError as exc:
            raise PasswordResetValidationError(str(exc)) from exc

        now = datetime.now(UTC)
        token = self._repository.get_token_for_update(
            token_hash=hash_action_token(raw_token),
            purpose="password_reset",
        )
        if token is None or not self._is_usable(token, now=now):
            self._repository.rollback()
            raise InvalidAccountActionTokenError
        user = token.user
        if user.state != "active":
            self._repository.rollback()
            raise InvalidAccountActionTokenError
        user.password_hash = password_hash
        user.updated_at = now
        token.consumed_at = now
        self._repository.revoke_open_tokens(
            user_id=user.id, purpose="password_reset", now=now
        )
        self._repository.revoke_user_sessions(user.id, now)
        self._repository.add_event(
            "password_reset_completed", user_id=user.id, ip_address=ip_address
        )
        self._repository.commit()

    def _issue_token(
        self,
        *,
        user: User,
        purpose: str,
        lifetime: timedelta,
        event_type: str,
        ip_address: str | None,
    ) -> str:
        now = datetime.now(UTC)
        self._repository.revoke_open_tokens(
            user_id=user.id, purpose=purpose, now=now
        )
        raw_token = token_urlsafe(32)
        self._repository.add_token(
            AccountActionToken(
                user_id=user.id,
                purpose=purpose,
                token_hash=hash_action_token(raw_token),
                created_at=now,
                expires_at=now + lifetime,
            )
        )
        self._repository.add_event(
            event_type, user_id=user.id, ip_address=ip_address
        )
        self._repository.commit()
        return raw_token

    @staticmethod
    def _is_usable(token: AccountActionToken, *, now: datetime) -> bool:
        return (
            token.consumed_at is None
            and token.revoked_at is None
            and now < utc_value(token.expires_at)
        )
