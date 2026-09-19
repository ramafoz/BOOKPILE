import argparse
import logging
from time import sleep
from uuid import uuid4

import sentry_sdk

from ..config import get_settings
from ..database import SessionFactory
from ..email_delivery import SmtpEmailSender
from ..email_outbox import EmailOutboxWorker
from ..error_reporting import capture_unhandled_error, initialize_error_reporting


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    parser.add_argument("--processed-delay-seconds", type=float, default=0.0)
    args = parser.parse_args()
    if args.poll_seconds < 0.25 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 0.25 and 60")
    if args.processed_delay_seconds < 0 or args.processed_delay_seconds > 3600:
        parser.error("--processed-delay-seconds must be between 0 and 3600")
    settings = get_settings()
    initialize_error_reporting(settings)
    worker = EmailOutboxWorker(
        SessionFactory,
        SmtpEmailSender(settings),
        settings,
    )
    try:
        if args.once:
            return 0 if worker.process_one() else 2
        while True:
            processed = worker.process_one()
            sleep(args.processed_delay_seconds if processed else args.poll_seconds)
    except Exception as exc:
        capture_unhandled_error(
            exc,
            correlation_id=uuid4().hex,
            component="email-worker",
            settings=settings,
        )
        sentry_sdk.flush(timeout=5)
        raise


if __name__ == "__main__":
    raise SystemExit(main())
