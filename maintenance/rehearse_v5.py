import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.migrations import (  # noqa: E402
    connect_database,
    copy_backup_for_rehearsal,
    run_migrations,
    schema_version,
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("backup", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    database, covers = copy_backup_for_rehearsal(
        args.backup.resolve(), args.destination.resolve()
    )
    report = run_migrations(
        database,
        covers=covers,
        backup_directory=args.destination / "backups",
        approved=True,
    )
    connection = connect_database(database)
    try:
        session_row = connection.execute(
            """
            SELECT COUNT(*) AS total,
                   SUM(state = 'ACTIVE') AS active,
                   SUM(state = 'COMPLETED') AS completed,
                   SUM(dates_unknown = 1) AS unknown
            FROM reading_sessions
            """
        ).fetchone()
        result = {
            "source": report.source_version,
            "target": report.target_version,
            "applied": report.applied_versions,
            "before_fingerprint": report.before_fingerprint,
            "after_fingerprint": report.after_fingerprint,
            "preserved_data_match": (
                report.before_fingerprint == report.after_fingerprint
            ),
            "schema": schema_version(connection),
            "sessions": dict(session_row),
            "completed_known": connection.execute(
                """
                SELECT COUNT(*) FROM reading_sessions
                WHERE state = 'COMPLETED' AND dates_unknown = 0
                """
            ).fetchone()[0],
            "integrity": connection.execute(
                "PRAGMA integrity_check"
            ).fetchone()[0],
            "foreign_key_errors": len(
                connection.execute("PRAGMA foreign_key_check").fetchall()
            ),
            "books": connection.execute("SELECT COUNT(*) FROM books").fetchone()[0],
            "covers": len(list(covers.glob("*.webp"))),
            "book_authors": connection.execute(
                "SELECT COUNT(*) FROM book_authors"
            ).fetchone()[0],
        }
        print(json.dumps(result, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
