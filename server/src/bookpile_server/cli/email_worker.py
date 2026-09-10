import argparse
from time import sleep

from ..config import get_settings
from ..database import SessionFactory
from ..email_delivery import SmtpEmailSender
from ..email_outbox import EmailOutboxWorker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--poll-seconds", type=float, default=2.0)
    args = parser.parse_args()
    if args.poll_seconds < 0.25 or args.poll_seconds > 60:
        parser.error("--poll-seconds must be between 0.25 and 60")
    settings = get_settings()
    worker = EmailOutboxWorker(
        SessionFactory,
        SmtpEmailSender(settings),
        settings,
    )
    if args.once:
        return 0 if worker.process_one() else 2
    while True:
        if not worker.process_one():
            sleep(args.poll_seconds)


if __name__ == "__main__":
    raise SystemExit(main())

