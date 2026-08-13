import sqlite3
from datetime import date
from typing import Any


class ReadingSessionError(ValueError):
    pass


def _as_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


def list_sessions(connection: sqlite3.Connection, book_id: int) -> list[dict[str, Any]]:
    return [
        dict(row)
        for row in connection.execute(
            """
            SELECT id, book_id, session_number, state, started_date,
                   finished_date, dates_unknown, created_at, updated_at
            FROM reading_sessions
            WHERE book_id = ?
            ORDER BY session_number
            """,
            (book_id,),
        )
    ]


def _book(connection: sqlite3.Connection, book_id: int) -> sqlite3.Row:
    row = connection.execute(
        "SELECT id, acquisition_date FROM books WHERE id = ?", (book_id,)
    ).fetchone()
    if row is None:
        raise ReadingSessionError("Book not found")
    return row


def _validate_known_dates(
    connection: sqlite3.Connection,
    book_id: int,
    started: date,
    finished: date | None,
) -> None:
    if started > date.today() or (finished is not None and finished > date.today()):
        raise ReadingSessionError("Reading dates cannot be in the future")
    if finished is not None and finished < started:
        raise ReadingSessionError(
            "Finished reading date cannot be earlier than reading started date"
        )
    acquired = _as_date(_book(connection, book_id)["acquisition_date"])
    if acquired is not None and started < acquired:
        raise ReadingSessionError(
            "Reading started date cannot be earlier than acquisition date"
        )


def _validate_timeline(connection: sqlite3.Connection, book_id: int) -> None:
    sessions = list_sessions(connection, book_id)
    unknown = [session for session in sessions if session["dates_unknown"]]
    if len(unknown) > 1:
        raise ReadingSessionError("Only one reading with unknown dates is allowed")
    active = [session for session in sessions if session["state"] == "ACTIVE"]
    if len(active) > 1:
        raise ReadingSessionError("Only one active reading is allowed")

    known = [
        session for session in sessions
        if not session["dates_unknown"] and session["started_date"]
    ]
    known.sort(
        key=lambda item: (
            item["started_date"],
            item["finished_date"] or "9999-12-31",
            item["id"],
        )
    )
    for previous, current in zip(known, known[1:]):
        previous_end = previous["finished_date"]
        if previous_end is None:
            raise ReadingSessionError("An active reading must be the last session")
        if current["started_date"] < previous_end:
            raise ReadingSessionError(
                "This reading session overlaps with "
                f'Reading {previous["session_number"]}: '
                f'{previous["started_date"]} – {previous_end}'
            )
        if (
            previous["started_date"] == previous_end
            and current["started_date"] == current["finished_date"]
            and current["started_date"] == previous["started_date"]
        ):
            raise ReadingSessionError(
                "Two one-day readings cannot be recorded for the same book on the same day"
            )


def renumber_sessions(connection: sqlite3.Connection, book_id: int) -> None:
    sessions = list_sessions(connection, book_id)
    sessions.sort(
        key=lambda item: (
            0 if item["dates_unknown"] else 1,
            item["started_date"] or "",
            item["finished_date"] or "9999-12-31",
            item["id"],
        )
    )
    # Temporary high values avoid the per-book unique constraint while rows
    # exchange positions without violating the positive-number check.
    for index, session in enumerate(sessions, 1):
        connection.execute(
            "UPDATE reading_sessions SET session_number = ? WHERE id = ?",
            (1000000 + index, session["id"]),
        )
    for index, session in enumerate(sessions, 1):
        connection.execute(
            """
            UPDATE reading_sessions
            SET session_number = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (index, session["id"]),
        )


def sync_book_projection(connection: sqlite3.Connection, book_id: int) -> None:
    sessions = list_sessions(connection, book_id)
    active = next((item for item in sessions if item["state"] == "ACTIVE"), None)
    latest = active or (sessions[-1] if sessions else None)
    if active:
        values = ("CURRENTLY_READING", active["started_date"], None, 0)
    elif latest:
        values = (
            "READ",
            latest["started_date"],
            latest["finished_date"],
            int(latest["dates_unknown"]),
        )
    else:
        values = ("PENDING", None, None, 0)
    connection.execute(
        """
        UPDATE books
        SET status = ?, reading_started_date = ?, read_date = ?,
            is_read_date_unknown = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (*values, book_id),
    )


def _finalize_change(connection: sqlite3.Connection, book_id: int) -> None:
    _validate_timeline(connection, book_id)
    renumber_sessions(connection, book_id)
    sync_book_projection(connection, book_id)


def start_reading(connection: sqlite3.Connection, book_id: int, started: date) -> int:
    _validate_known_dates(connection, book_id, started, None)
    if any(item["state"] == "ACTIVE" for item in list_sessions(connection, book_id)):
        raise ReadingSessionError("This book already has an active reading")
    cursor = connection.execute(
        """
        INSERT INTO reading_sessions (
            book_id, session_number, state, started_date, dates_unknown
        ) VALUES (?, ?, 'ACTIVE', ?, 0)
        """,
        (book_id, len(list_sessions(connection, book_id)) + 1, started.isoformat()),
    )
    _finalize_change(connection, book_id)
    return int(cursor.lastrowid)


def finish_reading(connection: sqlite3.Connection, book_id: int, finished: date) -> int:
    active = connection.execute(
        "SELECT * FROM reading_sessions WHERE book_id = ? AND state = 'ACTIVE'",
        (book_id,),
    ).fetchone()
    if active is None:
        raise ReadingSessionError("This book has no active reading to finish")
    started = _as_date(active["started_date"])
    assert started is not None
    _validate_known_dates(connection, book_id, started, finished)
    connection.execute(
        """
        UPDATE reading_sessions
        SET state = 'COMPLETED', finished_date = ?, updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (finished.isoformat(), active["id"]),
    )
    _finalize_change(connection, book_id)
    return int(active["id"])


def cancel_active_reading(connection: sqlite3.Connection, book_id: int) -> None:
    cursor = connection.execute(
        "DELETE FROM reading_sessions WHERE book_id = ? AND state = 'ACTIVE'",
        (book_id,),
    )
    if cursor.rowcount == 0:
        raise ReadingSessionError("This book has no active reading to cancel")
    _finalize_change(connection, book_id)


def add_historical_reading(
    connection: sqlite3.Connection,
    book_id: int,
    *,
    started: date | None,
    finished: date | None,
    dates_unknown: bool,
) -> int:
    sessions = list_sessions(connection, book_id)
    if dates_unknown:
        if started is not None or finished is not None:
            raise ReadingSessionError("Unknown reading dates must both be empty")
        if any(item["dates_unknown"] for item in sessions):
            raise ReadingSessionError("Only one reading with unknown dates is allowed")
    else:
        if started is None or finished is None:
            raise ReadingSessionError("Completed readings require both dates")
        _validate_known_dates(connection, book_id, started, finished)
    cursor = connection.execute(
        """
        INSERT INTO reading_sessions (
            book_id, session_number, state, started_date, finished_date,
            dates_unknown
        ) VALUES (?, ?, 'COMPLETED', ?, ?, ?)
        """,
        (
            book_id,
            len(sessions) + 1,
            started.isoformat() if started else None,
            finished.isoformat() if finished else None,
            int(dates_unknown),
        ),
    )
    _finalize_change(connection, book_id)
    return int(cursor.lastrowid)


def update_session(
    connection: sqlite3.Connection,
    book_id: int,
    session_id: int,
    *,
    started: date | None,
    finished: date | None,
    dates_unknown: bool,
) -> None:
    session = connection.execute(
        "SELECT * FROM reading_sessions WHERE id = ? AND book_id = ?",
        (session_id, book_id),
    ).fetchone()
    if session is None:
        raise ReadingSessionError("Reading session not found")
    if session["state"] == "ACTIVE":
        if dates_unknown or started is None or finished is not None:
            raise ReadingSessionError("An active reading requires a known start date")
        _validate_known_dates(connection, book_id, started, None)
    elif dates_unknown:
        if started is not None or finished is not None:
            raise ReadingSessionError("Unknown reading dates must both be empty")
    else:
        if started is None or finished is None:
            raise ReadingSessionError("Completed readings require both dates")
        _validate_known_dates(connection, book_id, started, finished)
    connection.execute(
        """
        UPDATE reading_sessions
        SET started_date = ?, finished_date = ?, dates_unknown = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
        """,
        (
            started.isoformat() if started else None,
            finished.isoformat() if finished else None,
            int(dates_unknown),
            session_id,
        ),
    )
    _finalize_change(connection, book_id)


def delete_session(connection: sqlite3.Connection, book_id: int, session_id: int) -> None:
    cursor = connection.execute(
        "DELETE FROM reading_sessions WHERE id = ? AND book_id = ?",
        (session_id, book_id),
    )
    if cursor.rowcount == 0:
        raise ReadingSessionError("Reading session not found")
    _finalize_change(connection, book_id)


def delete_all_sessions(connection: sqlite3.Connection, book_id: int) -> int:
    cursor = connection.execute(
        "DELETE FROM reading_sessions WHERE book_id = ?", (book_id,)
    )
    sync_book_projection(connection, book_id)
    return cursor.rowcount


def apply_projected_reading_values(
    connection: sqlite3.Connection,
    book_id: int,
    *,
    status: str,
    started: date | None,
    finished: date | None,
    dates_unknown: bool,
) -> None:
    """Compatibility bridge for the v4 book editor.

    The history table remains authoritative; legacy fields edit the active or
    latest completed session instead of becoming an independent source.
    """
    sessions = list_sessions(connection, book_id)
    active = next((item for item in sessions if item["state"] == "ACTIVE"), None)
    latest = sessions[-1] if sessions else None
    if status == "PENDING":
        delete_all_sessions(connection, book_id)
        return
    if status == "CURRENTLY_READING":
        if started is None:
            raise ReadingSessionError("An active reading requires a start date")
        if active:
            update_session(
                connection, book_id, active["id"],
                started=started, finished=None, dates_unknown=False,
            )
        else:
            start_reading(connection, book_id, started)
        return
    if active:
        if dates_unknown:
            raise ReadingSessionError("An active reading cannot finish with unknown dates")
        if finished is None:
            raise ReadingSessionError("Finishing a reading requires a finish date")
        finish_reading(connection, book_id, finished)
        return
    if latest:
        update_session(
            connection, book_id, latest["id"],
            started=started, finished=finished, dates_unknown=dates_unknown,
        )
    else:
        add_historical_reading(
            connection, book_id, started=started, finished=finished,
            dates_unknown=dates_unknown,
        )
