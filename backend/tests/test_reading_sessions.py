from datetime import date

import pytest

from app.database import connect, init_database
from app.reading_sessions import (
    ReadingSessionError,
    add_historical_reading,
    cancel_active_reading,
    delete_session,
    finish_reading,
    list_sessions,
    start_reading,
    update_session,
)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    """Never allow reading-session tests to touch the live catalogue."""
    monkeypatch.setenv("BOOKPILE_DATABASE", str(tmp_path / "bookpile.db"))


def create_book() -> int:
    init_database()
    with connect() as connection:
        return int(connection.execute(
            "INSERT INTO books (title, author) VALUES ('Test', 'Reader')"
        ).lastrowid)


def test_reading_and_rereading_keep_a_complete_projection() -> None:
    book_id = create_book()
    with connect() as connection:
        start_reading(connection, book_id, date(2026, 1, 1))
        finish_reading(connection, book_id, date(2026, 1, 5))
        start_reading(connection, book_id, date(2026, 2, 1))
        row = connection.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        assert row["status"] == "CURRENTLY_READING"
        assert row["reading_started_date"] == "2026-02-01"
        assert row["read_date"] is None
        cancel_active_reading(connection, book_id)
        row = connection.execute("SELECT * FROM books WHERE id = ?", (book_id,)).fetchone()
        assert row["status"] == "READ"
        assert row["reading_started_date"] == "2026-01-01"
        assert row["read_date"] == "2026-01-05"


def test_unknown_history_is_unique_first_and_renumbered() -> None:
    book_id = create_book()
    with connect() as connection:
        known_id = add_historical_reading(
            connection, book_id,
            started=date(2024, 5, 1), finished=date(2024, 5, 3),
            dates_unknown=False,
        )
        add_historical_reading(
            connection, book_id, started=None, finished=None, dates_unknown=True
        )
        sessions = list_sessions(connection, book_id)
        assert sessions[0]["dates_unknown"] == 1
        assert sessions[1]["id"] == known_id
        with pytest.raises(ReadingSessionError, match="Only one"):
            add_historical_reading(
                connection, book_id, started=None, finished=None,
                dates_unknown=True,
            )


def test_overlap_is_rejected_but_touching_boundaries_are_allowed() -> None:
    book_id = create_book()
    with connect() as connection:
        add_historical_reading(
            connection, book_id,
            started=date(2026, 3, 10), finished=date(2026, 3, 15),
            dates_unknown=False,
        )
        add_historical_reading(
            connection, book_id,
            started=date(2026, 3, 15), finished=date(2026, 3, 15),
            dates_unknown=False,
        )
        with pytest.raises(ReadingSessionError, match="overlaps"):
            add_historical_reading(
                connection, book_id,
                started=date(2026, 3, 14), finished=date(2026, 3, 16),
                dates_unknown=False,
            )


def test_delete_renumbers_and_last_delete_returns_pending() -> None:
    book_id = create_book()
    with connect() as connection:
        first = add_historical_reading(
            connection, book_id,
            started=date(2025, 1, 1), finished=date(2025, 1, 2),
            dates_unknown=False,
        )
        second = add_historical_reading(
            connection, book_id,
            started=date(2025, 2, 1), finished=date(2025, 2, 2),
            dates_unknown=False,
        )
        delete_session(connection, book_id, first)
        assert list_sessions(connection, book_id)[0]["session_number"] == 1
        delete_session(connection, book_id, second)
        row = connection.execute("SELECT status FROM books WHERE id = ?", (book_id,)).fetchone()
        assert row["status"] == "PENDING"


def test_active_session_requires_known_start_and_cannot_be_future() -> None:
    book_id = create_book()
    with connect() as connection:
        with pytest.raises(ReadingSessionError, match="future"):
            start_reading(connection, book_id, date(2099, 1, 1))
