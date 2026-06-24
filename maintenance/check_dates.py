from __future__ import annotations

import argparse
from datetime import date

from common import connect_read_only, report_path, write_csv


def audit_dates(include_future: bool = True) -> list[dict]:
    issues: list[dict] = []
    today = date.today().isoformat()
    with connect_read_only() as connection:
        books = connection.execute(
            """
            SELECT
                id, title, author, status,
                acquisition_date, reading_started_date, read_date,
                is_original_collection, is_read_date_unknown
            FROM books
            ORDER BY title COLLATE NOCASE, author COLLATE NOCASE
            """
        ).fetchall()

    for book in books:
        acquisition = book["acquisition_date"]
        started = book["reading_started_date"]
        finished = book["read_date"]

        def add(code: str, message: str, severity: str = "ERROR") -> None:
            issues.append(
                {
                    "severity": severity,
                    "code": code,
                    "book_id": book["id"],
                    "title": book["title"],
                    "author": book["author"],
                    "status": book["status"],
                    "acquisition_date": acquisition or "",
                    "reading_started_date": started or "",
                    "read_date": finished or "",
                    "message": message,
                }
            )

        if book["is_original_collection"] and acquisition:
            add(
                "ORIGINAL_WITH_ACQUISITION_DATE",
                "Original-collection book still has an acquisition date.",
            )
        if acquisition and started and started < acquisition:
            add("START_BEFORE_ACQUISITION", "Reading started before acquisition.")
        if started and finished and finished < started:
            add("FINISH_BEFORE_START", "Reading finished before reading started.")
        if acquisition and finished and finished < acquisition:
            add("FINISH_BEFORE_ACQUISITION", "Reading finished before acquisition.")
        if book["is_read_date_unknown"] and book["status"] != "READ":
            add(
                "UNKNOWN_READ_DATE_WITH_NON_READ_STATUS",
                "Reading date is marked unknown but status is not Read.",
            )
        if book["is_read_date_unknown"] and finished:
            add(
                "UNKNOWN_READ_DATE_WITH_DATE",
                "Reading date is marked unknown but a finish date is present.",
            )
        if (
            book["status"] == "READ"
            and not finished
            and not book["is_read_date_unknown"]
        ):
            add(
                "READ_WITHOUT_DATE_EXPLANATION",
                "Read book has no finish date and is not marked date unknown.",
                "WARNING",
            )
        if book["status"] == "CURRENTLY_READING" and finished:
            add(
                "CURRENTLY_READING_WITH_FINISH_DATE",
                "Currently-reading book already has a finish date.",
                "WARNING",
            )
        if include_future:
            for field, value in (
                ("acquisition", acquisition),
                ("reading started", started),
                ("reading finished", finished),
            ):
                if value and value > today:
                    add(
                        "FUTURE_DATE",
                        f"{field.title()} date is in the future.",
                        "WARNING",
                    )

    return issues


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Read-only audit of BOOKPILE lifecycle dates."
    )
    parser.add_argument(
        "--ignore-future",
        action="store_true",
        help="Do not report dates later than today.",
    )
    args = parser.parse_args()

    issues = audit_dates(include_future=not args.ignore_future)
    errors = sum(issue["severity"] == "ERROR" for issue in issues)
    warnings = len(issues) - errors

    print(f"Date audit: {errors} errors, {warnings} warnings.")
    if not issues:
        print("No date issues found.")
        return 0

    path = report_path("date-audit")
    write_csv(path, issues[0].keys(), issues)
    for issue in issues:
        print(
            f'[{issue["severity"]}] #{issue["book_id"]} '
            f'{issue["title"]}: {issue["message"]}'
        )
    print(f"\nCSV report: {path}")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
