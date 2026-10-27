import argparse
from datetime import timedelta
import json

from ..database import SessionFactory
from ..defensive_metrics import aggregate_lease_conflicts


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-minutes", type=int, default=15)
    args = parser.parse_args()
    if args.window_minutes < 1 or args.window_minutes > 1440:
        parser.error("--window-minutes must be between 1 and 1440")
    with SessionFactory() as session:
        payload = aggregate_lease_conflicts(
            session,
            window=timedelta(minutes=args.window_minutes),
        )
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
