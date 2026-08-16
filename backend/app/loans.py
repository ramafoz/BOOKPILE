import sqlite3
from datetime import date
from typing import Any


class LoanError(ValueError):
    pass


def _as_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def _clean_required(value: str) -> str:
    cleaned = " ".join(value.split())
    if not cleaned:
        raise LoanError("Loaned to is required")
    if len(cleaned) > 300:
        raise LoanError("Loaned to cannot exceed 300 characters")
    return cleaned


def _clean_notes(value: str | None) -> str | None:
    cleaned = value.strip() if value else ""
    if len(cleaned) > 4000:
        raise LoanError("Loan notes cannot exceed 4000 characters")
    return cleaned or None


def _book_exists(connection: sqlite3.Connection, book_id: int) -> None:
    if connection.execute(
        "SELECT 1 FROM books WHERE id = ?", (book_id,)
    ).fetchone() is None:
        raise LoanError("Book not found")


def validate_loan_dates(
    *,
    loaned_date: date | None,
    expected_return_date: date | None,
    returned_date: date | None,
) -> None:
    today = date.today()
    if loaned_date is not None and loaned_date > today:
        raise LoanError("Loan date cannot be in the future")
    if returned_date is not None and returned_date > today:
        raise LoanError("Returned date cannot be in the future")
    if (
        loaned_date is not None
        and expected_return_date is not None
        and expected_return_date < loaned_date
    ):
        raise LoanError("Expected return date cannot be earlier than loan date")
    if (
        loaned_date is not None
        and returned_date is not None
        and returned_date < loaned_date
    ):
        raise LoanError("Returned date cannot be earlier than loan date")


def list_loans(connection: sqlite3.Connection, book_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, book_id, loaned_to, notes, state, loaned_date,
                   expected_return_date, returned_date, created_at, updated_at
            FROM loans
            WHERE book_id = ?
            ORDER BY
                CASE
                    WHEN state = 'ACTIVE' THEN 2
                    WHEN loaned_date IS NULL THEN 0
                    ELSE 1
                END,
                loaned_date,
                created_at,
                id
            """,
            (book_id,),
        )
    ]


def active_loan(
    connection: sqlite3.Connection, book_id: int
) -> dict[str, Any] | None:
    row = connection.execute(
        """
        SELECT id, book_id, loaned_to, notes, state, loaned_date,
               expected_return_date, returned_date, created_at, updated_at
        FROM loans WHERE book_id = ? AND state = 'ACTIVE'
        """,
        (book_id,),
    ).fetchone()
    return dict(row) if row else None


def start_loan(
    connection: sqlite3.Connection,
    book_id: int,
    *,
    loaned_to: str,
    loaned_date: date | None,
    expected_return_date: date | None,
    notes: str | None,
) -> int:
    _book_exists(connection, book_id)
    if active_loan(connection, book_id):
        raise LoanError("This book already has an active loan")
    validate_loan_dates(
        loaned_date=loaned_date,
        expected_return_date=expected_return_date,
        returned_date=None,
    )
    cursor = connection.execute(
        """
        INSERT INTO loans (
            book_id, loaned_to, notes, state, loaned_date,
            expected_return_date, returned_date
        ) VALUES (?, ?, ?, 'ACTIVE', ?, ?, NULL)
        """,
        (
            book_id,
            _clean_required(loaned_to),
            _clean_notes(notes),
            loaned_date.isoformat() if loaned_date else None,
            expected_return_date.isoformat() if expected_return_date else None,
        ),
    )
    return int(cursor.lastrowid)


def return_loan(
    connection: sqlite3.Connection,
    book_id: int,
    *,
    returned_date: date | None,
) -> int:
    loan = active_loan(connection, book_id)
    if loan is None:
        raise LoanError("This book has no active loan to return")
    validate_loan_dates(
        loaned_date=_as_date(loan["loaned_date"]),
        expected_return_date=_as_date(loan["expected_return_date"]),
        returned_date=returned_date,
    )
    connection.execute(
        """
        UPDATE loans
        SET state = 'RETURNED', returned_date = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (returned_date.isoformat() if returned_date else None, loan["id"]),
    )
    return int(loan["id"])


def cancel_active_loan(connection: sqlite3.Connection, book_id: int) -> None:
    cursor = connection.execute(
        "DELETE FROM loans WHERE book_id = ? AND state = 'ACTIVE'", (book_id,)
    )
    if cursor.rowcount == 0:
        raise LoanError("This book has no active loan to cancel")


def add_historical_loan(
    connection: sqlite3.Connection,
    book_id: int,
    *,
    loaned_to: str,
    loaned_date: date | None,
    expected_return_date: date | None,
    returned_date: date | None,
    notes: str | None,
) -> int:
    _book_exists(connection, book_id)
    validate_loan_dates(
        loaned_date=loaned_date,
        expected_return_date=expected_return_date,
        returned_date=returned_date,
    )
    cursor = connection.execute(
        """
        INSERT INTO loans (
            book_id, loaned_to, notes, state, loaned_date,
            expected_return_date, returned_date
        ) VALUES (?, ?, ?, 'RETURNED', ?, ?, ?)
        """,
        (
            book_id,
            _clean_required(loaned_to),
            _clean_notes(notes),
            loaned_date.isoformat() if loaned_date else None,
            expected_return_date.isoformat() if expected_return_date else None,
            returned_date.isoformat() if returned_date else None,
        ),
    )
    return int(cursor.lastrowid)


def update_loan(
    connection: sqlite3.Connection,
    book_id: int,
    loan_id: int,
    *,
    loaned_to: str,
    loaned_date: date | None,
    expected_return_date: date | None,
    returned_date: date | None,
    notes: str | None,
) -> None:
    loan = connection.execute(
        "SELECT * FROM loans WHERE id = ? AND book_id = ?", (loan_id, book_id)
    ).fetchone()
    if loan is None:
        raise LoanError("Loan record not found")
    if loan["state"] == "ACTIVE" and returned_date is not None:
        raise LoanError("Use Return book to complete an active loan")
    validate_loan_dates(
        loaned_date=loaned_date,
        expected_return_date=expected_return_date,
        returned_date=returned_date,
    )
    connection.execute(
        """
        UPDATE loans
        SET loaned_to = ?, notes = ?, loaned_date = ?,
            expected_return_date = ?, returned_date = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            _clean_required(loaned_to),
            _clean_notes(notes),
            loaned_date.isoformat() if loaned_date else None,
            expected_return_date.isoformat() if expected_return_date else None,
            returned_date.isoformat() if returned_date else None,
            loan_id,
        ),
    )


def delete_loan(connection: sqlite3.Connection, book_id: int, loan_id: int) -> None:
    cursor = connection.execute(
        "DELETE FROM loans WHERE id = ? AND book_id = ?", (loan_id, book_id)
    )
    if cursor.rowcount == 0:
        raise LoanError("Loan record not found")
