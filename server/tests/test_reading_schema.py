from datetime import date

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bookpile_server.models import (
    Book,
    Library,
    PersonalBookRecord,
    ReadingSession,
    User,
)


def fixture_records(session: Session):
    first_library = Library(name="First", slug="reading-first")
    second_library = Library(name="Second", slug="reading-second")
    first_user = User(
        email="first-reader@example.test",
        username="first_reader",
        password_hash="not-a-real-hash",
        state="active",
    )
    second_user = User(
        email="second-reader@example.test",
        username="second_reader",
        password_hash="not-a-real-hash",
        state="active",
    )
    session.add_all([first_library, second_library, first_user, second_user])
    session.flush()
    first_book = Book(
        library_id=first_library.id, title="One", author="Author"
    )
    second_book = Book(
        library_id=second_library.id, title="Two", author="Author"
    )
    session.add_all([first_book, second_book])
    session.commit()
    return first_library, second_library, first_book, second_book, first_user, second_user


def test_schema_accepts_personal_history_and_review_without_membership_fk(
    session: Session,
) -> None:
    library, _, book, _, user, _ = fixture_records(session)
    session.add_all(
        [
            ReadingSession(
                library_id=library.id,
                book_id=book.id,
                user_id=user.id,
                state="COMPLETED",
                started_date=date(2026, 1, 1),
                finished_date=date(2026, 1, 2),
            ),
            PersonalBookRecord(
                library_id=library.id,
                book_id=book.id,
                user_id=user.id,
                goodreads_url="https://www.goodreads.com/review/show/1",
            ),
        ]
    )
    session.commit()
    assert session.query(ReadingSession).count() == 1
    assert session.query(PersonalBookRecord).count() == 1


@pytest.mark.parametrize(
    ("state", "started", "finished", "unknown"),
    [
        ("ACTIVE", None, None, False),
        ("ACTIVE", date(2026, 1, 1), date(2026, 1, 2), False),
        ("COMPLETED", date(2026, 1, 1), None, False),
        ("COMPLETED", None, date(2026, 1, 2), False),
        ("COMPLETED", date(2026, 1, 1), date(2026, 1, 2), True),
        ("COMPLETED", date(2026, 1, 2), date(2026, 1, 1), False),
    ],
)
def test_database_rejects_invalid_session_shapes(
    session: Session, state: str, started, finished, unknown: bool
) -> None:
    library, _, book, _, user, _ = fixture_records(session)
    session.add(
        ReadingSession(
            library_id=library.id,
            book_id=book.id,
            user_id=user.id,
            state=state,
            started_date=started,
            finished_date=finished,
            dates_unknown=unknown,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_cross_library_book_scope(session: Session) -> None:
    library, _, _, other_book, user, _ = fixture_records(session)
    session.add(
        ReadingSession(
            library_id=library.id,
            book_id=other_book.id,
            user_id=user.id,
            state="ACTIVE",
            started_date=date(2026, 1, 1),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_allows_only_one_active_reader_per_copy(session: Session) -> None:
    library, _, book, _, first_user, second_user = fixture_records(session)
    session.add(
        ReadingSession(
            library_id=library.id,
            book_id=book.id,
            user_id=first_user.id,
            state="ACTIVE",
            started_date=date(2026, 1, 1),
        )
    )
    session.commit()
    session.add(
        ReadingSession(
            library_id=library.id,
            book_id=book.id,
            user_id=second_user.id,
            state="ACTIVE",
            started_date=date(2026, 1, 2),
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_database_allows_only_one_unknown_reading_and_personal_record(
    session: Session,
) -> None:
    library, _, book, _, user, _ = fixture_records(session)
    session.add(
        ReadingSession(
            library_id=library.id,
            book_id=book.id,
            user_id=user.id,
            state="COMPLETED",
            dates_unknown=True,
        )
    )
    session.commit()
    session.add(
        ReadingSession(
            library_id=library.id,
            book_id=book.id,
            user_id=user.id,
            state="COMPLETED",
            dates_unknown=True,
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()

    session.rollback()
    session.add_all(
        [
            PersonalBookRecord(
                library_id=library.id, book_id=book.id, user_id=user.id
            ),
            PersonalBookRecord(
                library_id=library.id, book_id=book.id, user_id=user.id
            ),
        ]
    )
    with pytest.raises(IntegrityError):
        session.commit()
