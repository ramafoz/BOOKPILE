from dataclasses import dataclass
from datetime import UTC, datetime
from email.message import EmailMessage
from email.utils import format_datetime, parseaddr
from hashlib import sha256
import re
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
    html: str | None = None
    account_action_token_id: UUID | None = None
    account_deletion_tombstone_id: UUID | None = None


@dataclass(frozen=True)
class SmtpDeliveryReceipt:
    response_code: int
    provider_queue_id: str | None = None


class EmailSender(Protocol):
    def send(self, email: OutgoingEmail) -> SmtpDeliveryReceipt | None: ...


class EmailDeliveryError(Exception):
    pass


class _ReceiptMixin:
    last_data_response: tuple[int, bytes] | None = None

    def data(self, msg):
        response = super().data(msg)
        self.last_data_response = response
        return response


class ReceiptSMTP(_ReceiptMixin, smtplib.SMTP):
    pass


class ReceiptSMTPSSL(_ReceiptMixin, smtplib.SMTP_SSL):
    pass


QUEUE_ID_PATTERN = re.compile(
    r"(?:queued\s+as|queue(?:\s+id)?[=:]?)\s*<?([A-Za-z0-9-]{5,64})>?",
    re.IGNORECASE,
)


def _delivery_receipt(
    response: tuple[int, bytes] | None,
) -> SmtpDeliveryReceipt | None:
    if response is None:
        return None
    code, raw_message = response
    response_text = raw_message.decode("ascii", errors="replace")
    match = QUEUE_ID_PATTERN.search(response_text)
    return SmtpDeliveryReceipt(
        response_code=code,
        provider_queue_id=match.group(1) if match else None,
    )


class SmtpEmailSender:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def send(self, email: OutgoingEmail) -> SmtpDeliveryReceipt | None:
        message = EmailMessage()
        message["From"] = self._settings.smtp_from_email
        message["To"] = email.recipient
        message["Subject"] = email.subject
        message["Date"] = format_datetime(datetime.now(UTC))
        message["Auto-Submitted"] = "auto-generated"
        message["X-Auto-Response-Suppress"] = "All"
        sender_domain = parseaddr(self._settings.smtp_from_email)[1].partition("@")[2]
        message_hash = sha256(email.message_key.encode("utf-8")).hexdigest()
        message["Message-ID"] = f"<{message_hash}@{sender_domain or 'bookpile.invalid'}>"
        message.set_content(email.text)
        if email.html:
            message.add_alternative(email.html, subtype="html")
        try:
            smtp_client = ReceiptSMTPSSL if self._settings.smtp_implicit_tls else ReceiptSMTP
            client_options = {
                "host": self._settings.smtp_host,
                "port": self._settings.smtp_port,
                "timeout": self._settings.smtp_timeout_seconds,
            }
            if self._settings.smtp_implicit_tls:
                client_options["context"] = ssl.create_default_context()
            with smtp_client(
                **client_options,
            ) as smtp:
                if self._settings.smtp_starttls:
                    smtp.starttls(context=ssl.create_default_context())
                if self._settings.smtp_username and self._settings.smtp_password:
                    smtp.login(
                        self._settings.smtp_username,
                        self._settings.smtp_password.get_secret_value(),
                    )
                smtp.send_message(message)
                return _delivery_receipt(smtp.last_data_response)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("Email delivery failed.") from exc
