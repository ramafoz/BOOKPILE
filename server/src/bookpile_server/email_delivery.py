from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
from typing import Protocol

from .config import Settings


@dataclass(frozen=True)
class OutgoingEmail:
    recipient: str
    subject: str
    text: str


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
        message.set_content(email.text)
        try:
            with smtplib.SMTP(
                self._settings.smtp_host,
                self._settings.smtp_port,
                timeout=10,
            ) as smtp:
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Email delivery failed.") from exc
