from email.utils import parsedate_to_datetime
from hashlib import sha256
from unittest.mock import MagicMock, patch

from bookpile_server.config import Settings
from bookpile_server.email_delivery import OutgoingEmail, SmtpEmailSender


def test_smtp_sender_uses_implicit_tls_when_configured() -> None:
    settings = Settings(
        smtp_host="smtp-secure.example.com",
        smtp_port=465,
        smtp_from_email="BOOKPILE <hello@bookpile.gal>",
        smtp_implicit_tls=True,
        smtp_username="hello@bookpile.gal",
        smtp_password="mailbox-password",
    )
    connection = MagicMock()
    smtp = connection.__enter__.return_value
    smtp.last_data_response = (250, b"2.0.0 Ok: queued as PROVIDER123")
    email = OutgoingEmail(
        recipient="reader@example.com",
        subject="BOOKPILE — Verify your email",
        text="Verification message",
        html="<html><body><p>Verification message</p></body></html>",
        message_key="verification:test",
        purpose="EMAIL_VERIFICATION",
    )

    with (
        patch("bookpile_server.email_delivery.ReceiptSMTPSSL", return_value=connection) as smtp_ssl,
        patch("bookpile_server.email_delivery.ReceiptSMTP") as smtp_starttls,
    ):
        receipt = SmtpEmailSender(settings).send(email)

    smtp_ssl.assert_called_once()
    assert smtp_ssl.call_args.kwargs["host"] == settings.smtp_host
    assert smtp_ssl.call_args.kwargs["port"] == 465
    assert smtp_ssl.call_args.kwargs["context"].check_hostname
    smtp_starttls.assert_not_called()
    smtp.starttls.assert_not_called()
    smtp.login.assert_called_once_with("hello@bookpile.gal", "mailbox-password")
    smtp.send_message.assert_called_once()
    message = smtp.send_message.call_args.args[0]
    assert parsedate_to_datetime(message["Date"]).tzinfo is not None
    assert message["Auto-Submitted"] == "auto-generated"
    assert message["X-Auto-Response-Suppress"] == "All"
    assert message["Message-ID"] == (
        f"<{sha256(email.message_key.encode()).hexdigest()}@bookpile.gal>"
    )
    assert message.is_multipart()
    assert message.get_body(preferencelist=("plain",)).get_content().strip() == email.text
    assert email.html in message.get_body(preferencelist=("html",)).get_content()
    assert receipt is not None
    assert receipt.response_code == 250
    assert receipt.provider_queue_id == "PROVIDER123"
