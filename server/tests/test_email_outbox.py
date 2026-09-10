from datetime import UTC, datetime, timedelta
import logging
from uuid import uuid4

from sqlalchemy.orm import sessionmaker

from bookpile_server.config import get_settings
from bookpile_server.email_delivery import EmailDeliveryError, OutgoingEmail
from bookpile_server.email_outbox import EmailOutboxWorker, TransactionalOutboxEmailSender
from bookpile_server.models import AccountActionToken, EmailOutboxMessage, User


class Delivery:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.emails: list[OutgoingEmail] = []

    def send(self, email: OutgoingEmail) -> None:
        if self.fail:
            raise EmailDeliveryError("unavailable")
        self.emails.append(email)


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
    delivery = Delivery()
    worker = EmailOutboxWorker(sessionmaker(bind=session.get_bind()), delivery, get_settings())

    assert worker.process_one()

    session.expire_all()
    assert session.get(EmailOutboxMessage, message.id).state == "SENT"
    assert delivery.emails[0].text == "secret-link-token"
    assert "email_sent" in caplog.text
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
