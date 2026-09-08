from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Book,
    LibraryAuditEvent,
    LibraryMembership,
    Loan,
    PersonalBookRecord,
    ReadingSession,
    User,
)


class ReadingRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def membership(
        self, *, library_id: UUID, user_id: UUID
    ) -> LibraryMembership | None:
        return self._session.scalar(
            select(LibraryMembership).where(
                LibraryMembership.library_id == library_id,
                LibraryMembership.user_id == user_id,
            )
        )

    def book(self, *, library_id: UUID, book_id: UUID) -> Book | None:
        return self._session.scalar(
            select(Book).where(Book.library_id == library_id, Book.id == book_id)
        )

    def lock_book(self, *, library_id: UUID, book_id: UUID) -> Book | None:
        return self._session.scalar(
            select(Book)
            .where(Book.library_id == library_id, Book.id == book_id)
            .with_for_update()
        )

    def sessions(
        self, *, library_id: UUID, book_id: UUID, user_id: UUID
    ) -> list[ReadingSession]:
        return list(
            self._session.scalars(
                select(ReadingSession)
                .where(
                    ReadingSession.library_id == library_id,
                    ReadingSession.book_id == book_id,
                    ReadingSession.user_id == user_id,
                )
                .order_by(
                    ReadingSession.dates_unknown.desc(),
                    ReadingSession.started_date,
                    ReadingSession.finished_date,
                    ReadingSession.created_at,
                    ReadingSession.id,
                )
            )
        )

    def library_book_ids(self, *, library_id: UUID) -> list[UUID]:
        return list(self._session.scalars(select(Book.id).where(Book.library_id == library_id)))

    def library_books(self, *, library_id: UUID) -> list[Book]:
        return list(
            self._session.scalars(
                select(Book).where(Book.library_id == library_id).order_by(Book.title, Book.id)
            )
        )

    def library_sessions(
        self, *, library_id: UUID, user_id: UUID
    ) -> list[ReadingSession]:
        return list(
            self._session.scalars(
                select(ReadingSession).where(
                    ReadingSession.library_id == library_id,
                    ReadingSession.user_id == user_id,
                )
            )
        )

    def active_book_ids(self, *, library_id: UUID) -> set[UUID]:
        return set(
            self._session.scalars(
                select(ReadingSession.book_id).where(
                    ReadingSession.library_id == library_id,
                    ReadingSession.state == "ACTIVE",
                )
            )
        )

    def personal_records(
        self, *, library_id: UUID, user_id: UUID
    ) -> list[PersonalBookRecord]:
        return list(
            self._session.scalars(
                select(PersonalBookRecord).where(
                    PersonalBookRecord.library_id == library_id,
                    PersonalBookRecord.user_id == user_id,
                )
            )
        )

    def session(
        self, *, library_id: UUID, book_id: UUID, session_id: UUID
    ) -> ReadingSession | None:
        return self._session.scalar(
            select(ReadingSession).where(
                ReadingSession.library_id == library_id,
                ReadingSession.book_id == book_id,
                ReadingSession.id == session_id,
            )
        )

    def active_for_book(
        self, *, library_id: UUID, book_id: UUID
    ) -> ReadingSession | None:
        return self._session.scalar(
            select(ReadingSession).where(
                ReadingSession.library_id == library_id,
                ReadingSession.book_id == book_id,
                ReadingSession.state == "ACTIVE",
            )
        )

    def active_loan_for_book(
        self, *, library_id: UUID, book_id: UUID
    ) -> Loan | None:
        return self._session.scalar(
            select(Loan).where(
                Loan.library_id == library_id,
                Loan.book_id == book_id,
                Loan.state == "ACTIVE",
            )
        )

    def personal_record(
        self, *, library_id: UUID, book_id: UUID, user_id: UUID
    ) -> PersonalBookRecord | None:
        return self._session.scalar(
            select(PersonalBookRecord).where(
                PersonalBookRecord.library_id == library_id,
                PersonalBookRecord.book_id == book_id,
                PersonalBookRecord.user_id == user_id,
            )
        )

    def reviews(
        self, *, library_id: UUID, book_id: UUID
    ) -> list[tuple[PersonalBookRecord, str]]:
        return list(
            self._session.execute(
                select(PersonalBookRecord, User.username)
                .join(User, User.id == PersonalBookRecord.user_id)
                .join(
                    LibraryMembership,
                    (LibraryMembership.library_id == PersonalBookRecord.library_id)
                    & (LibraryMembership.user_id == PersonalBookRecord.user_id),
                )
                .where(
                    PersonalBookRecord.library_id == library_id,
                    PersonalBookRecord.book_id == book_id,
                    PersonalBookRecord.goodreads_url.is_not(None),
                    LibraryMembership.role == "OWNER",
                )
                .order_by(User.username, User.id)
            )
        )

    def username(self, user_id: UUID) -> str | None:
        return self._session.scalar(select(User.username).where(User.id == user_id))

    def add(self, record: ReadingSession | PersonalBookRecord) -> None:
        self._session.add(record)

    def delete(self, record: ReadingSession | PersonalBookRecord) -> None:
        self._session.delete(record)

    def audit(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        event_type: str,
        details: dict[str, object],
    ) -> None:
        self._session.add(
            LibraryAuditEvent(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                details=details,
            )
        )

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        from ..services.storage_transactions import commit_with_storage

        commit_with_storage(self._session)

    def rollback(self) -> None:
        self._session.rollback()
