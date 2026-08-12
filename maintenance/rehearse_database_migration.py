from __future__ import annotations

import argparse
import json
import sys
import tempfile
from contextlib import closing
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.exports import create_full_backup  # noqa: E402
from app.migrations import (  # noqa: E402
    LATEST_SCHEMA_VERSION,
    connect_database,
    copy_backup_for_rehearsal,
    run_migrations,
    schema_version,
)
from app.restore import extract_and_validate_archive  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate a BOOKPILE backup and rehearse pending database migrations "
            "inside a disposable temporary directory. The live database is never opened."
        )
    )
    parser.add_argument("backup", type=Path, help="Full BOOKPILE backup ZIP")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    backup = args.backup.resolve()
    if not backup.is_file():
        raise SystemExit(f"Backup not found: {backup}")

    with tempfile.TemporaryDirectory(prefix="bookpile-migration-rehearsal-") as temp:
        root = Path(temp)
        database, covers = copy_backup_for_rehearsal(
            backup,
            root / "catalogue-before",
        )
        migration_backups = root / "automatic-backups"
        report = run_migrations(
            database,
            covers=covers,
            backup_directory=migration_backups,
            approved=True,
        )

        with closing(connect_database(database)) as connection:
            counts = {
                table: connection.execute(
                    f'SELECT COUNT(*) FROM "{table}"'
                ).fetchone()[0]
                for table in ("bookcases", "shelves", "containers", "books")
            }
            resulting_version = schema_version(connection)
            null_isbn_count = connection.execute(
                """
                SELECT COUNT(*) FROM books
                WHERE isbn_10 IS NULL AND isbn_13 IS NULL
                """
            ).fetchone()[0]
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_errors = len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            )

        post_migration_backup = root / "post-migration-v2.zip"
        post_manifest = create_full_backup(
            post_migration_backup,
            source_database=database,
            source_covers=covers,
        )
        post_validation = extract_and_validate_archive(
            post_migration_backup,
            root / "post-migration-validation",
        )

        result = {
            "source_backup": str(backup),
            "live_database_opened": False,
            "source_schema_version": report.source_version,
            "target_schema_version": report.target_version,
            "resulting_schema_version": resulting_version,
            "latest_supported_schema_version": LATEST_SCHEMA_VERSION,
            "applied_versions": report.applied_versions,
            "automatic_backup_created_and_validated": bool(report.backup_path),
            "catalogue_fingerprint_before": report.before_fingerprint,
            "catalogue_fingerprint_after": report.after_fingerprint,
            "existing_values_preserved": (
                report.before_fingerprint == report.after_fingerprint
            ),
            "counts": counts,
            "covers": len(list(covers.glob("*.webp"))),
            "books_with_both_isbns_null": null_isbn_count,
            "integrity_check": integrity,
            "foreign_key_errors": foreign_key_errors,
            "post_migration_backup_schema_version": post_manifest["schema_version"],
            "post_migration_backup_validated": (
                post_validation["schema_version"] == resulting_version
            ),
            "temporary_rehearsal_deleted_on_exit": True,
        }
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
