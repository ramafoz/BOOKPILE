from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    Book,
    LibraryAuditEvent,
    LibraryMembership,
    Loan,
    ReadingSession,
)


class LoanRepository:
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

    def history(self, *, library_id: UUID, book_id: UUID) -> list[Loan]:
        return list(
            self._session.scalars(
                select(Loan)
                .where(Loan.library_id == library_id, Loan.book_id == book_id)
                .order_by(
                    Loan.loaned_date.is_not(None),
                    Loan.loaned_date,
                    Loan.returned_date,
                    Loan.created_at,
                    Loan.id,
                )
            )
        )

    def loan(
        self, *, library_id: UUID, book_id: UUID, loan_id: UUID
    ) -> Loan | None:
        return self._session.scalar(
            select(Loan).where(
                Loan.library_id == library_id,
                Loan.book_id == book_id,
                Loan.id == loan_id,
            )
        )

    def active(self, *, library_id: UUID, book_id: UUID) -> Loan | None:
        return self._session.scalar(
            select(Loan).where(
                Loan.library_id == library_id,
                Loan.book_id == book_id,
                Loan.state == "ACTIVE",
            )
        )

    def active_for_library(self, *, library_id: UUID) -> list[Loan]:
        return list(
            self._session.scalars(
                select(Loan)
                .where(Loan.library_id == library_id, Loan.state == "ACTIVE")
                .order_by(Loan.expected_return_date, Loan.created_at, Loan.id)
            )
        )

    def history_for_library(self, *, library_id: UUID) -> list[tuple[Loan, Book]]:
        return list(
            self._session.execute(
                select(Loan, Book)
                .join(Book, (Book.library_id == Loan.library_id) & (Book.id == Loan.book_id))
                .where(Loan.library_id == library_id)
                .order_by(Loan.created_at, Loan.id)
            ).all()
        )

    def active_reading(
        self, *, library_id: UUID, book_id: UUID
    ) -> ReadingSession | None:
        return self._session.scalar(
            select(ReadingSession).where(
                ReadingSession.library_id == library_id,
                ReadingSession.book_id == book_id,
                ReadingSession.state == "ACTIVE",
            )
        )

    def add(self, loan: Loan) -> None:
        self._session.add(loan)

    def delete(self, loan: Loan) -> None:
        self._session.delete(loan)

    def audit(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        event_type: str,
        book_id: UUID,
        loan_id: UUID,
    ) -> None:
        # Borrower identity and notes are deliberately forbidden here.
        self._session.add(
            LibraryAuditEvent(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                details={"book_id": str(book_id), "loan_id": str(loan_id)},
            )
        )

    def flush(self) -> None:
        self._session.flush()

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
