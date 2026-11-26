"""Enrol or revoke a BOOKPILE Server platform administrator from a trusted host."""

import argparse
from getpass import GetPassWarning, getpass
import os
import re
from secrets import compare_digest, token_urlsafe
import sys
from time import monotonic
from uuid import UUID, uuid4
import warnings

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError

from ..config import Settings
from ..email_delivery import EmailDeliveryError, EmailSender, OutgoingEmail, SmtpEmailSender
from ..platform_enrolment import (
    ENROLMENT_REASONS,
    EnrolmentRequest,
    prepare_first_passkey,
    record_enrolment,
    target_is_eligible,
)
from ..security.identities import normalize_email


CONFIRMATION_SECONDS = 600
OPERATOR_ID = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_.-]{0,63}")


class EnrolmentError(ValueError):
    pass


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("enrol", "revoke", "prepare-passkey"))
    parser.add_argument("user_id", type=UUID)
    parser.add_argument("--operator", required=True, help="Opaque operator identifier")
    parser.add_argument("--reason", required=True, choices=ENROLMENT_REASONS)
    return parser.parse_args()


def _confirm_by_email(
    request: EnrolmentRequest, environment: str, recipient: str, sender: EmailSender
) -> bool:
    code = token_urlsafe(16)
    expiry = monotonic() + CONFIRMATION_SECONDS
    try:
        sender.send(
            OutgoingEmail(
                recipient=recipient,
                subject="BOOKPILE Server platform role confirmation",
                text=(
                    f"Confirm {request.action} for {environment} in your host terminal.\n"
                    f"Reference: {request.correlation_id}\n"
                    f"Single-use code (expires in 10 minutes): {code}\n"
                    "Ignore this message if you did not initiate this action."
                ),
                message_key=f"platform-admin-confirmation-{request.correlation_id}",
                purpose="platform_admin_confirmation",
            )
        )
        with warnings.catch_warnings():
            warnings.simplefilter("error", GetPassWarning)
            supplied = getpass(f"Email confirmation code ({request.correlation_id}): ")
        return monotonic() < expiry and compare_digest(code.encode(), supplied.encode())
    except (EmailDeliveryError, EOFError, GetPassWarning, KeyboardInterrupt, OSError):
        return False


def _send_passkey_confirmation(
    request: EnrolmentRequest, environment: str, recipient: str, sender: EmailSender, code: str,
) -> bool:
    try:
        sender.send(OutgoingEmail(
            recipient=recipient,
            subject="BOOKPILE Server first passkey confirmation",
            text=(f"Confirm first passkey registration for {environment} on /admin-access.\n"
                  f"Reference: {request.correlation_id}\n"
                  f"Single-use code (expires in 10 minutes): {code}\n"
                  "Ignore this message if you did not initiate this action."),
            message_key=f"platform-passkey-{request.correlation_id}",
            purpose="platform_admin_confirmation",
        ))
    except EmailDeliveryError:
        return False
    return True


def main() -> int:
    args = _arguments()
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty() and sys.stderr.isatty()):
            raise EnrolmentError("Platform administration requires an interactive terminal.")
        if not OPERATOR_ID.fullmatch(args.operator):
            raise EnrolmentError("Use an opaque operator identifier.")
        environment = os.environ.get("BOOKPILE_PLATFORM_ADMIN_ENVIRONMENT", "")
        if environment not in {"staging", "production", "test"}:
            raise EnrolmentError("Select a platform administration environment.")
        database_url = make_url(os.environ.get("BOOKPILE_PLATFORM_ADMIN_DATABASE_URL", ""))
        if not (
            database_url.drivername in {"postgresql", "postgresql+psycopg"}
            and database_url.host and database_url.database
            and (environment != "test" or database_url.database.endswith("_test"))
        ):
            raise EnrolmentError("Configure the PostgreSQL host administration credential.")
        operator_email = normalize_email(os.environ.get("BOOKPILE_PLATFORM_ADMIN_OPERATOR_EMAIL", ""))
        settings = Settings(_env_file=None)
        if not (
            (settings.smtp_starttls or settings.smtp_implicit_tls)
            and settings.smtp_username and settings.smtp_password
        ):
            raise EnrolmentError("Configure authenticated SMTP with TLS for operator confirmation.")

        request = EnrolmentRequest(
            args.action, args.user_id, args.operator, args.reason, uuid4()
        )
        typed = f"{request.action.upper()} {request.target}"
        if input(f"To {request.action} SYSTEM_ADMIN in {environment}, type {typed}: ") != typed:
            raise EnrolmentError("Typed confirmation did not match.")

        engine = create_engine(
            database_url.set(drivername="postgresql+psycopg"),
            hide_parameters=True,
            connect_args={"connect_timeout": 5},
        )
        try:
            with engine.connect() as connection:
                if not connection.scalar(text(
                    "SELECT rolsuper FROM pg_catalog.pg_roles WHERE rolname = current_user"
                )):
                    raise EnrolmentError("Use the isolated host migrator credential.")
            sender = SmtpEmailSender(settings)
            if request.action == "prepare-passkey":
                code = token_urlsafe(32)
                changed = prepare_first_passkey(
                    engine, request, operator_email, code,
                    lambda: _send_passkey_confirmation(request, environment, operator_email, sender, code),
                )
            else:
                eligible = target_is_eligible(engine, request, operator_email)
                confirmed = eligible and _confirm_by_email(request, environment, operator_email, sender)
                changed = record_enrolment(engine, request, operator_email, confirmed=confirmed)
        finally:
            engine.dispose()

        if not changed:
            print(f"Platform access unchanged. Audit reference {request.correlation_id}.", file=sys.stderr)
            return 1
        print(f"Platform access updated. Audit reference {request.correlation_id}.")
        return 0
    except EnrolmentError as exc:
        print(str(exc), file=sys.stderr)
    except (ValueError, EOFError, KeyboardInterrupt, SQLAlchemyError, OSError):
        print("Platform administration did not complete. Check the host configuration or audit reference.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
