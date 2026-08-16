from datetime import date, timedelta

import pytest

from app.database import connect, init_database
from app.loans import (
    LoanError,
    add_historical_loan,
    cancel_active_loan,
    delete_loan,
    list_loans,
    return_loan,
    start_loan,
    update_loan,
)


@pytest.fixture(autouse=True)
def isolated_database(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKPILE_DATABASE", str(tmp_path / "bookpile.db"))


def create_book() -> int:
    init_database()
    with connect() as connection:
        return int(connection.execute(
            "INSERT INTO books (title, author) VALUES ('Loan test', 'Author')"
        ).lastrowid)


def test_active_loan_can_have_unknown_date_and_is_unique() -> None:
    book_id = create_book()
    with connect() as connection:
        loan_id = start_loan(
            connection,
            book_id,
            loaned_to="  María   Example  ",
            loaned_date=None,
            expected_return_date=date.today() + timedelta(days=7),
            notes="  Handle carefully  ",
        )
        with pytest.raises(LoanError, match="already has an active loan"):
            start_loan(
                connection,
                book_id,
                loaned_to="Someone else",
                loaned_date=date.today(),
                expected_return_date=None,
                notes=None,
            )
        loan = list_loans(connection, book_id)[0]
        assert loan["id"] == loan_id
        assert loan["loaned_to"] == "María Example"
        assert loan["loaned_date"] is None
        assert loan["notes"] == "Handle carefully"
        assert loan["state"] == "ACTIVE"


def test_return_with_unknown_date_and_cancel_are_distinct() -> None:
    book_id = create_book()
    with connect() as connection:
        start_loan(
            connection, book_id, loaned_to="Friend", loaned_date=None,
            expected_return_date=None, notes=None,
        )
        return_loan(connection, book_id, returned_date=None)
        assert list_loans(connection, book_id)[0]["state"] == "RETURNED"

        start_loan(
            connection, book_id, loaned_to="Other", loaned_date=date.today(),
            expected_return_date=None, notes=None,
        )
        cancel_active_loan(connection, book_id)
        loans = list_loans(connection, book_id)
        assert len(loans) == 1
        assert loans[0]["loaned_to"] == "Friend"


def test_historical_loans_order_unknown_records_before_known_dates() -> None:
    book_id = create_book()
    with connect() as connection:
        first_unknown = add_historical_loan(
            connection, book_id, loaned_to="First", loaned_date=None,
            expected_return_date=None, returned_date=None, notes=None,
        )
        second_unknown = add_historical_loan(
            connection, book_id, loaned_to="Second", loaned_date=None,
            expected_return_date=None, returned_date=date(2020, 1, 1), notes=None,
        )
        known = add_historical_loan(
            connection, book_id, loaned_to="Known", loaned_date=date(2021, 1, 1),
            expected_return_date=date(2021, 2, 1),
            returned_date=date(2021, 1, 20), notes=None,
        )
        assert [loan["id"] for loan in list_loans(connection, book_id)] == [
            first_unknown, second_unknown, known,
        ]


def test_dates_and_history_updates_are_validated() -> None:
    book_id = create_book()
    with connect() as connection:
        with pytest.raises(LoanError, match="future"):
            start_loan(
                connection, book_id, loaned_to="Friend",
                loaned_date=date.today() + timedelta(days=1),
                expected_return_date=None, notes=None,
            )
        with pytest.raises(LoanError, match="Expected return"):
            add_historical_loan(
                connection, book_id, loaned_to="Friend",
                loaned_date=date(2024, 2, 1),
                expected_return_date=date(2024, 1, 1),
                returned_date=None, notes=None,
            )
        loan_id = add_historical_loan(
            connection, book_id, loaned_to="Old friend",
            loaned_date=date(2024, 1, 1), expected_return_date=None,
            returned_date=date(2024, 1, 2), notes=None,
        )
        update_loan(
            connection, book_id, loan_id, loaned_to="Corrected friend",
            loaned_date=None, expected_return_date=None,
            returned_date=None, notes="Unknown dates",
        )
        assert list_loans(connection, book_id)[0]["loaned_to"] == "Corrected friend"
        delete_loan(connection, book_id, loan_id)
        assert list_loans(connection, book_id) == []
