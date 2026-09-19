import argparse
import json

from ..api.dependencies import get_private_object_storage
from ..config import get_settings
from ..database import SessionFactory
from ..operations import collect_operations_status, run_maintenance


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run")
    check = subparsers.add_parser("check")
    check.add_argument("--deep", action="store_true")
    args = parser.parse_args()
    storage = get_private_object_storage()
    with SessionFactory() as session:
        if args.command == "run":
            payload = run_maintenance(
                session,
                storage,
                get_settings().import_staging_root,
            ).payload()
            exit_code = 0
        else:
            status = collect_operations_status(session, storage, deep=args.deep)
            payload = status.payload()
            exit_code = 0 if status.healthy else 1
    print(json.dumps(payload, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
