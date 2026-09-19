import json

import sentry_sdk

from ..config import get_settings
from ..error_reporting import (
    capture_unhandled_error,
    initialize_error_reporting,
)


def main() -> int:
    settings = get_settings()
    if not initialize_error_reporting(settings):
        print(json.dumps({"configured": False, "sent": False}, separators=(",", ":")))
        return 2
    try:
        raise RuntimeError("controlled BOOKPILE error-reporting probe")
    except RuntimeError as exc:
        event_id = capture_unhandled_error(
            exc,
            correlation_id="error-reporting-probe",
            component="probe",
            settings=settings,
        )
    sentry_sdk.flush(timeout=10)
    print(
        json.dumps(
            {
                "configured": True,
                "event_id": event_id,
                "sent": event_id is not None,
            },
            separators=(",", ":"),
        )
    )
    return 0 if event_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
