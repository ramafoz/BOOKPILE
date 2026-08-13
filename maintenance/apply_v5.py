import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.exports import create_full_backup, sha256_file  # noqa: E402
from app.migrations import connect_database, run_migrations, schema_version  # noqa: E402
from app.restore import extract_and_validate_archive  # noqa: E402


def main() -> None:
    database = ROOT / "backend" / "data" / "bookpile.db"
    covers = ROOT / "backend" / "data" / "covers"
    backups = ROOT / "backend" / "backups"
    report = run_migrations(
        database,
        covers=covers,
        backup_directory=backups,
        approved=True,
    )
    post_backup = backups / "BOOKPILE-after-migration-v5.zip"
    manifest = create_full_backup(post_backup)
    validation_root = ROOT / ".bookpile-runtime" / "v5-post-backup-validation"
    if validation_root.exists():
        import shutil
        shutil.rmtree(validation_root)
    validation = extract_and_validate_archive(post_backup, validation_root)

    connection = connect_database(database)
    try:
        sessions = dict(connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(state = 'ACTIVE') AS active,
                   SUM(state = 'COMPLETED') AS completed,
                   SUM(dates_unknown = 1) AS unknown
            FROM reading_sessions
            """
        ).fetchone())
        result = {
            "source": report.source_version,
            "target": report.target_version,
            "applied": report.applied_versions,
            "pre_migration_backup": str(report.backup_path),
            "pre_migration_backup_sha256": (
                sha256_file(report.backup_path) if report.backup_path else None
            ),
            "preserved_data_match": (
                report.before_fingerprint == report.after_fingerprint
            ),
            "schema": schema_version(connection),
            "sessions": sessions,
            "books": connection.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            "covers": len(list(covers.glob("*.webp"))),
            "book_authors": connection.execute(
                "SELECT COUNT(*) FROM book_authors"
            ).fetchone()[0],
            "integrity": connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0],
            "foreign_key_errors": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "post_backup": str(post_backup),
            "post_backup_sha256": sha256_file(post_backup),
            "post_backup_counts": manifest["counts"],
            "post_backup_validated_counts": validation["counts"],
        }
        print(json.dumps(result, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
