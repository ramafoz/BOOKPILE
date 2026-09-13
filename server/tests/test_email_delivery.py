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
    email = OutgoingEmail(
        recipient="reader@example.com",
        subject="Verify your BOOKPILE account",
        text="Verification message",
        message_key="verification:test",
        purpose="EMAIL_VERIFICATION",
    )

    with (
        patch("bookpile_server.email_delivery.smtplib.SMTP_SSL", return_value=connection) as smtp_ssl,
        patch("bookpile_server.email_delivery.smtplib.SMTP") as smtp_starttls,
    ):
        SmtpEmailSender(settings).send(email)

    smtp_ssl.assert_called_once()
    assert smtp_ssl.call_args.kwargs["host"] == settings.smtp_host
    assert smtp_ssl.call_args.kwargs["port"] == 465
    assert smtp_ssl.call_args.kwargs["context"].check_hostname
    smtp_starttls.assert_not_called()
    smtp.starttls.assert_not_called()
    smtp.login.assert_called_once_with("hello@bookpile.gal", "mailbox-password")
    smtp.send_message.assert_called_once()
