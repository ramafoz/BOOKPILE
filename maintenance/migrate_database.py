from __future__ import annotations

import argparse
import json
import sys
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.database import database_path  # noqa: E402
from app.migrations import (  # noqa: E402
    LATEST_SCHEMA_VERSION,
    connect_database,
    pending_migrations,
    run_migrations,
    schema_version,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect or explicitly apply versioned BOOKPILE database migrations. "
            "Without --approve this command is read-only."
        )
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=database_path(),
        help="Database to inspect or migrate (defaults to the configured catalogue)",
    )
    parser.add_argument(
        "--covers",
        type=Path,
        help="Cover directory (defaults to a covers folder beside the database)",
    )
    parser.add_argument(
        "--backup-directory",
        type=Path,
        default=BACKEND_ROOT / "backups",
        help="Where the mandatory verified pre-migration ZIP is stored",
    )
    parser.add_argument(
        "--approve",
        action="store_true",
        help="Create and verify a backup, then apply all pending migrations",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    database = args.database.resolve()
    covers = (args.covers or database.parent / "covers").resolve()
    backup_directory = args.backup_directory.resolve()

    with closing(connect_database(database)) as connection:
        source_version = schema_version(connection)
    pending = pending_migrations(source_version)

    if not args.approve:
        print(
            json.dumps(
                {
                    "database": str(database),
                    "current_schema_version": source_version,
                    "latest_supported_schema_version": LATEST_SCHEMA_VERSION,
                    "pending_migrations": [
                        {"version": migration.version, "name": migration.name}
                        for migration in pending
                    ],
                    "changed": False,
                    "message": (
                        "Read-only inspection complete. Use --approve only after "
                        "reviewing a successful rehearsal and the recovery guide."
                    ),
                },
                indent=2,
            )
        )
        return 0

    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backup_directory,
        approved=True,
    )
    print(
        json.dumps(
            {
                "database": str(database),
                "source_schema_version": report.source_version,
                "target_schema_version": report.target_version,
                "applied_versions": report.applied_versions,
                "backup": str(report.backup_path) if report.backup_path else None,
                "existing_values_preserved": (
                    report.before_fingerprint == report.after_fingerprint
                ),
                "catalogue_fingerprint": report.after_fingerprint,
                "changed": bool(report.applied_versions),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
