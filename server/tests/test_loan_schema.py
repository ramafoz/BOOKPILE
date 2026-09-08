from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bookpile_server.models import Book, Library, Loan


def fixture_books(session: Session):
    first_library = Library(name="First", slug="loan-first")
    second_library = Library(name="Second", slug="loan-second")
    session.add_all([first_library, second_library])
    session.flush()
    first_book = Book(library_id=first_library.id, title="One", author="Author")
    second_book = Book(library_id=second_library.id, title="Two", author="Author")
    session.add_all([first_book, second_book])
    session.commit()
    return first_library, second_library, first_book, second_book


def test_schema_accepts_active_and_unknown_returned_history(session: Session) -> None:
    library, _, first_book, _ = fixture_books(session)
    session.add(
        Loan(
            library_id=library.id,
            book_id=first_book.id,
            state="ACTIVE",
            loaned_to="Alice",
            loaned_date=date(2026, 9, 1),
            expected_return_date=date(2026, 10, 1),
        )
    )
    session.commit()
    assert session.query(Loan).count() == 1


def test_schema_rejects_cross_library_scope(session: Session) -> None:
    library, _, _, other_book = fixture_books(session)
    session.add(
        Loan(
            library_id=library.id,
            book_id=other_book.id,
            state="ACTIVE",
            loaned_to="Alice",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_schema_allows_only_one_active_loan_per_copy(session: Session) -> None:
    library, _, book, _ = fixture_books(session)
    session.add(
        Loan(library_id=library.id, book_id=book.id, state="ACTIVE", loaned_to="Alice")
    )
    session.commit()
    session.add(
        Loan(library_id=library.id, book_id=book.id, state="ACTIVE", loaned_to="Bob")
    )
    with pytest.raises(IntegrityError):
        session.commit()


@pytest.mark.parametrize(
    ("state", "borrower", "loaned", "expected", "returned", "notes"),
    [
        ("BROKEN", "Alice", None, None, None, None),
        ("ACTIVE", "   ", None, None, None, None),
        ("ACTIVE", "Alice", None, None, date(2026, 1, 2), None),
        ("ACTIVE", "Alice", date(2026, 1, 2), date(2026, 1, 1), None, None),
        ("RETURNED", "Alice", date(2026, 1, 2), None, date(2026, 1, 1), None),
        ("RETURNED", "Alice", None, None, None, "n" * 4001),
    ],
)
def test_schema_rejects_invalid_loan_shapes(
    session: Session, state, borrower, loaned, expected, returned, notes
) -> None:
    library, _, book, _ = fixture_books(session)
    session.add(
        Loan(
            library_id=library.id,
            book_id=book.id,
            state=state,
            loaned_to=borrower,
            loaned_date=loaned,
            expected_return_date=expected,
            returned_date=returned,
            notes=notes,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()
