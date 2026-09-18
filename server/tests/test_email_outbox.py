from datetime import UTC, datetime, timedelta
import json
import logging
from hashlib import sha256
from secrets import token_bytes
from uuid import UUID, uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from sqlalchemy.orm import sessionmaker

from bookpile_server.config import get_settings
from bookpile_server.email_delivery import (
    EmailDeliveryError,
    OutgoingEmail,
    SmtpDeliveryReceipt,
)
from bookpile_server.email_outbox import (
    EmailOutboxWorker,
    EmailPayloadCipher,
    TransactionalOutboxEmailSender,
)
from bookpile_server.models import AccountActionToken, EmailOutboxMessage, User


class Delivery:
    def __init__(self, *, fail: bool = False, queue_id: str | None = None) -> None:
        self.fail = fail
        self.queue_id = queue_id
        self.emails: list[OutgoingEmail] = []

    def send(self, email: OutgoingEmail) -> SmtpDeliveryReceipt | None:
        if self.fail:
            raise EmailDeliveryError("unavailable")
        self.emails.append(email)
        if self.queue_id:
            return SmtpDeliveryReceipt(250, self.queue_id)
        return None


def enqueue(session, *, revoked: bool = False) -> EmailOutboxMessage:
    now = datetime.now(UTC)
    user = User(email=f"{uuid4()}@example.test", username=f"u{uuid4().hex[:10]}", password_hash="x")
    token = AccountActionToken(
        user=user,
        purpose="password_reset",
        token_hash=uuid4().hex,
        expires_at=now + timedelta(minutes=30),
        revoked_at=now if revoked else None,
    )
    session.add_all([user, token])
    session.flush()
    sender = TransactionalOutboxEmailSender(session, get_settings())
    sender.send(
        OutgoingEmail(
            recipient=user.email,
            subject="Reset",
            text="secret-link-token",
            html="<p>secret-link-token</p>",
            message_key=uuid4().hex,
            purpose="PASSWORD_RESET",
            account_action_token_id=token.id,
        )
    )
    session.commit()
    return session.query(EmailOutboxMessage).one()


def test_worker_delivers_encrypted_message_and_marks_it_sent(session, caplog) -> None:
    caplog.set_level(logging.INFO, logger="bookpile.email_outbox")
    message = enqueue(session)
    assert b"secret-link-token" not in message.payload_ciphertext
    delivery = Delivery(queue_id="SAFEQUEUE123")
    worker = EmailOutboxWorker(sessionmaker(bind=session.get_bind()), delivery, get_settings())

    assert worker.process_one()

    session.expire_all()
    stored = session.get(EmailOutboxMessage, message.id)
    assert stored.state == "SENT"
    assert stored.smtp_response_code == 250
    assert stored.provider_queue_id == "SAFEQUEUE123"
    assert delivery.emails[0].text == "secret-link-token"
    assert delivery.emails[0].html == "<p>secret-link-token</p>"
    assert "email_sent" in caplog.text
    assert '"smtp_response_code":250' in caplog.text
    assert '"provider_queue_id":"SAFEQUEUE123"' in caplog.text
    assert "secret-link-token" not in caplog.text
    assert delivery.emails[0].recipient not in caplog.text


def test_worker_retries_transient_delivery_failure(session) -> None:
    message = enqueue(session)
    worker = EmailOutboxWorker(
        sessionmaker(bind=session.get_bind()), Delivery(fail=True), get_settings()
    )

    assert worker.process_one()

    session.expire_all()
    stored = session.get(EmailOutboxMessage, message.id)
    assert stored.state == "PENDING"
    assert stored.attempt_count == 1
    assert stored.last_error_code == "DELIVERY_UNAVAILABLE"


def test_worker_cancels_message_whose_action_was_revoked(session) -> None:
    message = enqueue(session, revoked=True)
    delivery = Delivery()
    worker = EmailOutboxWorker(sessionmaker(bind=session.get_bind()), delivery, get_settings())

    assert worker.process_one()

    session.expire_all()
    assert session.get(EmailOutboxMessage, message.id).state == "CANCELLED"
    assert delivery.emails == []


def test_cipher_reads_legacy_plain_text_payload_without_html() -> None:
    settings = get_settings()
    message_id = UUID("3dc0b9f5-4470-4d47-ac39-14562becf268")
    payload = json.dumps(
        {
            "recipient": "legacy@example.test",
            "subject": "Legacy message",
            "text": "Legacy text",
            "message_key": "legacy:key",
            "purpose": "PASSWORD_RESET",
        },
        separators=(",", ":"),
    ).encode()
    secret = settings.email_outbox_encryption_secret.get_secret_value()
    cipher = AESGCM(sha256(secret.encode()).digest())
    nonce = token_bytes(12)
    message = EmailOutboxMessage(
        id=message_id,
        message_key="legacy:key",
        purpose="PASSWORD_RESET",
        payload_ciphertext=nonce + cipher.encrypt(nonce, payload, message_id.bytes),
        available_at=datetime.now(UTC),
    )

    decrypted = EmailPayloadCipher(secret).decrypt(message)

    assert decrypted.text == "Legacy text"
    assert decrypted.html is None
