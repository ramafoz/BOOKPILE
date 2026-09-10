from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from hashlib import sha256
import ssl
import smtplib
from typing import Protocol
from uuid import UUID

from .config import Settings


@dataclass(frozen=True)
class OutgoingEmail:
    recipient: str
    subject: str
    text: str
    message_key: str
    purpose: str
    account_action_token_id: UUID | None = None
    account_deletion_tombstone_id: UUID | None = None


class EmailSender(Protocol):
    def send(self, email: OutgoingEmail) -> None: ...


class EmailDeliveryError(Exception):
    pass


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, email: OutgoingEmail) -> None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = email.recipient
        message["Subject"] = email.subject
        sender_domain = parseaddr(self._settings.smtp_from_email)[1].partition("@")[2]
        message_hash = sha256(email.message_key.encode("utf-8")).hexdigest()
        message["Message-ID"] = f"<{message_hash}@{sender_domain or 'bookpile.invalid'}>"
        message.set_content(email.text)
        try:
            with smtplib.SMTP(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=self._settings.smtp_timeout_seconds,
            ) as smtp:
                if self._settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._settings.smtp_username and self._settings.smtp_password:
                    smtp.login(
                        self._settings.smtp_username,
                        self._settings.smtp_password.get_secret_value(),
                    )
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Email delivery failed.") from exc
