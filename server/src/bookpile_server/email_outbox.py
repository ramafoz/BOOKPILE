import json
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_bytes
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .config import Settings
from .email_delivery import EmailDeliveryError, EmailSender, OutgoingEmail
from .models import (
    AccountActionToken,
    AccountDeletionTombstone,
    EmailOutboxMessage,
)


ACCOUNT_ACTION_LIFETIMES = {
    "EMAIL_VERIFICATION": timedelta(hours=24),
    "PASSWORD_RESET": timedelta(minutes=30),
}
ACCOUNT_DELETION_RECOVERY_LIFETIME = timedelta(hours=48)
RETRY_DELAYS = (
    timedelta(minutes=1),
    timedelta(minutes=5),
    timedelta(minutes=15),
    timedelta(hours=1),
    timedelta(hours=3),
    timedelta(hours=6),
    timedelta(hours=12),
)


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class EmailPayloadCipher:
    def __init__(self, secret: str) -> None:
        self._cipher = AESGCM(sha256(secret.encode("utf-8")).digest())

    def encrypt(self, message_id: UUID, email: OutgoingEmail) -> bytes:
        payload = json.dumps(
            {
                "recipient": email.recipient,
                "subject": email.subject,
                "text": email.text,
                "message_key": email.message_key,
                "purpose": email.purpose,
            },
            separators=(",", ":"),
        ).encode("utf-8")
        nonce = token_bytes(12)
        return nonce + self._cipher.encrypt(nonce, payload, message_id.bytes)

    def decrypt(self, message: EmailOutboxMessage) -> OutgoingEmail:
        nonce, ciphertext = message.payload_ciphertext[:12], message.payload_ciphertext[12:]
        payload = json.loads(
            self._cipher.decrypt(nonce, ciphertext, message.id.bytes).decode("utf-8")
        )
        return OutgoingEmail(
            recipient=payload["recipient"],
            subject=payload["subject"],
            text=payload["text"],
            message_key=payload["message_key"],
            purpose=payload["purpose"],
            account_action_token_id=message.account_action_token_id,
            account_deletion_tombstone_id=message.account_deletion_tombstone_id,
        )


class TransactionalOutboxEmailSender:
    def __init__(self, session: Session, settings: Settings) -> None:
        self._session = session
        self._cipher = EmailPayloadCipher(
            settings.email_outbox_encryption_secret.get_secret_value()
        )

    def send(self, email: OutgoingEmail) -> None:
        message_id = uuid4()
        self._session.add(
            EmailOutboxMessage(
                id=message_id,
                message_key=email.message_key,
                purpose=email.purpose,
                payload_ciphertext=self._cipher.encrypt(message_id, email),
                account_action_token_id=email.account_action_token_id,
                account_deletion_tombstone_id=email.account_deletion_tombstone_id,
                available_at=datetime.now(UTC),
            )
        )


class EmailOutboxWorker:
    def __init__(
        self,
        session_factory,
        delivery: EmailSender,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._delivery = delivery
        self._settings = settings
        self._cipher = EmailPayloadCipher(
            settings.email_outbox_encryption_secret.get_secret_value()
        )

    def process_one(self, *, now: datetime | None = None) -> bool:
        moment = now or datetime.now(UTC)
        message_id = self._claim(moment)
        if message_id is None:
            return False
        with self._session_factory() as session:
            message = session.get(EmailOutboxMessage, message_id)
            if message is None:
                return True
            if not self._is_still_relevant(session, message):
                message.state = "CANCELLED"
                message.lease_until = None
                message.updated_at = moment
                session.commit()
                return True
            try:
                outgoing = self._cipher.decrypt(message)
            except Exception:
                self._mark_terminal(session, message, moment, "PAYLOAD_DECRYPTION")
                return True
        try:
            self._delivery.send(outgoing)
        except EmailDeliveryError:
            with self._session_factory() as session:
                message = session.get(EmailOutboxMessage, message_id)
                if message is not None:
                    self._retry_or_fail(session, message, moment)
            return True
        with self._session_factory() as session:
            message = session.scalar(
                select(EmailOutboxMessage)
                .where(EmailOutboxMessage.id == message_id)
                .with_for_update()
            )
            if message is None or message.state != "PROCESSING":
                return True
            message.state = "SENT"
            message.sent_at = moment
            message.lease_until = None
            message.last_error_code = None
            message.updated_at = moment
            self._extend_recovery_window(session, message, moment)
            session.commit()
        return True

    def _claim(self, moment: datetime) -> UUID | None:
        with self._session_factory() as session:
            message = session.scalar(
                select(EmailOutboxMessage)
                .where(
                    or_(
                        (EmailOutboxMessage.state == "PENDING")
                        & (EmailOutboxMessage.available_at <= moment),
                        (EmailOutboxMessage.state == "PROCESSING")
                        & (EmailOutboxMessage.lease_until <= moment),
                    )
                )
                .order_by(EmailOutboxMessage.available_at, EmailOutboxMessage.id)
                .with_for_update(skip_locked=True)
                .limit(1)
            )
            if message is None:
                return None
            message.state = "PROCESSING"
            message.attempt_count += 1
            message.lease_until = moment + timedelta(
                seconds=self._settings.email_outbox_lease_seconds
            )
            message.updated_at = moment
            message_id = message.id
            session.commit()
            return message_id

    @staticmethod
    def _is_still_relevant(session: Session, message: EmailOutboxMessage) -> bool:
        if message.account_action_token_id:
            token = session.get(AccountActionToken, message.account_action_token_id)
            return token is not None and token.revoked_at is None and token.consumed_at is None
        if message.account_deletion_tombstone_id:
            tombstone = session.get(
                AccountDeletionTombstone,
                message.account_deletion_tombstone_id,
            )
            return tombstone is not None and tombstone.state == "PENDING"
        return False

    def _retry_or_fail(
        self,
        session: Session,
        message: EmailOutboxMessage,
        moment: datetime,
    ) -> None:
        if message.state != "PROCESSING":
            return
        message.lease_until = None
        message.last_error_code = "DELIVERY_UNAVAILABLE"
        message.updated_at = moment
        if message.attempt_count >= self._settings.email_outbox_max_attempts:
            message.state = "FAILED"
            message.failed_at = moment
        else:
            message.state = "PENDING"
            delay_index = min(message.attempt_count - 1, len(RETRY_DELAYS) - 1)
            message.available_at = moment + RETRY_DELAYS[delay_index]
        session.commit()

    @staticmethod
    def _mark_terminal(
        session: Session,
        message: EmailOutboxMessage,
        moment: datetime,
        code: str,
    ) -> None:
        message.state = "FAILED"
        message.failed_at = moment
        message.lease_until = None
        message.last_error_code = code
        message.updated_at = moment
        session.commit()

    @staticmethod
    def _extend_recovery_window(
        session: Session,
        message: EmailOutboxMessage,
        moment: datetime,
    ) -> None:
        if message.account_action_token_id:
            token = session.get(AccountActionToken, message.account_action_token_id)
            lifetime = ACCOUNT_ACTION_LIFETIMES.get(message.purpose)
            if token is not None and lifetime is not None:
                token.expires_at = moment + lifetime
        if message.account_deletion_tombstone_id:
            tombstone = session.get(
                AccountDeletionTombstone,
                message.account_deletion_tombstone_id,
            )
            if tombstone is not None:
                delivered_until = moment + ACCOUNT_DELETION_RECOVERY_LIFETIME
                if utc_value(tombstone.recover_until) < delivered_until:
                    tombstone.recover_until = delivered_until

