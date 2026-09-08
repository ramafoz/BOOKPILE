from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from ..models import Book, Loan
from ..repositories.loans import LoanRepository
from .loan_domain import (
    LoanPeriod,
    LoanRuleViolation,
    LoanState,
    normalize_loaned_to,
    normalize_notes,
    is_overdue,
    order_loan_history,
    validate_loan,
)


class LoanNotFoundError(Exception):
    pass


class LoanAccessError(Exception):
    pass


class LoanValidationError(Exception):
    pass


class LoanConflictError(Exception):
    pass


@dataclass(frozen=True)
class ViewerLoanItem:
    id: UUID
    book_id: UUID
    state: str
    loaned_date: date | None
    expected_return_date: date | None
    returned_date: date | None
    created_at: datetime
    updated_at: datetime
    overdue: bool


@dataclass(frozen=True)
class OwnerLoanItem(ViewerLoanItem):
    loaned_to: str
    notes: str | None


@dataclass(frozen=True)
class LoanProjection:
    library_id: UUID
    book_id: UUID
    writable: bool
    owner_items: list[OwnerLoanItem] | None
    viewer_items: list[ViewerLoanItem] | None


@dataclass(frozen=True)
class LoanCatalogueProjection:
    library_id: UUID
    writable: bool
    total_active: int
    total_overdue: int
    owner_items: list[OwnerLoanItem] | None
    viewer_items: list[ViewerLoanItem] | None


@dataclass(frozen=True)
class LoanStatisticsBook:
    book_id: UUID
    title: str
    author: str
    loans: int


@dataclass(frozen=True)
class LoanStatisticsYear:
    year: int
    loans: int
    returns: int


@dataclass(frozen=True)
class LoanStatistics:
    active: int
    overdue: int
    completed: int
    unknown_loan_dates: int
    unknown_return_dates: int
    books: list[LoanStatisticsBook]
    years: list[LoanStatisticsYear]


def _period(record: Loan, order: int = 0) -> LoanPeriod:
    return LoanPeriod(
        state=LoanState(record.state),
        loaned_to=record.loaned_to,
        loaned_date=record.loaned_date,
        expected_return_date=record.expected_return_date,
        returned_date=record.returned_date,
        notes=record.notes,
        creation_order=order,
    )


class LoanService:
    def __init__(self, repository: LoanRepository) -> None:
        self._repository = repository

    def _member(self, library_id: UUID, user_id: UUID):
        membership = self._repository.membership(
            library_id=library_id, user_id=user_id
        )
        if membership is None:
            raise LoanNotFoundError
        return membership

    def _owner(self, library_id: UUID, user_id: UUID) -> None:
        if self._member(library_id, user_id).role != "OWNER":
            raise LoanAccessError("Only an Owner can change loan data.")

    def _book(self, library_id: UUID, book_id: UUID, *, lock: bool = False):
        book = (
            self._repository.lock_book(library_id=library_id, book_id=book_id)
            if lock
            else self._repository.book(library_id=library_id, book_id=book_id)
        )
        if book is None:
            raise LoanNotFoundError
        return book

    def projection(
        self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID
    ) -> LoanProjection:
        membership = self._member(library_id, actor_user_id)
        self._book(library_id, book_id)
        records = self._ordered(
            self._repository.history(library_id=library_id, book_id=book_id)
        )
        if membership.role == "OWNER":
            return LoanProjection(
                library_id,
                book_id,
                True,
                [self._owner_item(record) for record in records],
                None,
            )
        return LoanProjection(
            library_id,
            book_id,
            False,
            None,
            [self._viewer_item(record) for record in records],
        )

    def catalogue_overview(
        self, *, library_id: UUID, actor_user_id: UUID
    ) -> LoanCatalogueProjection:
        membership = self._member(library_id, actor_user_id)
        records = self._repository.active_for_library(library_id=library_id)
        overdue = sum(is_overdue(_period(record)) for record in records)
        if membership.role == "OWNER":
            return LoanCatalogueProjection(
                library_id,
                True,
                len(records),
                overdue,
                [self._owner_item(record) for record in records],
                None,
            )
        return LoanCatalogueProjection(
            library_id,
            False,
            len(records),
            overdue,
            None,
            [self._viewer_item(record) for record in records],
        )

    def statistics(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        language: str | None = None,
        genre: str | None = None,
        publisher: str | None = None,
        loan_year: int | None = None,
    ) -> LoanStatistics:
        self._member(library_id, actor_user_id)
        rows = self._repository.history_for_library(library_id=library_id)
        if language:
            rows = [(loan, book) for loan, book in rows if book.language == language]
        if publisher:
            rows = [(loan, book) for loan, book in rows if book.publisher == publisher]
        if genre:
            target = genre.casefold()
            rows = [(loan, book) for loan, book in rows if target in (book.genre_text or "").casefold()]
        if loan_year:
            rows = [(loan, book) for loan, book in rows if loan.loaned_date and loan.loaned_date.year == loan_year]
        book_counts: dict[UUID, tuple[Book, int]] = {}
        years: dict[int, list[int]] = {}
        for loan, book in rows:
            book_counts[book.id] = (book, book_counts.get(book.id, (book, 0))[1] + 1)
            if loan.loaned_date:
                bucket = years.setdefault(loan.loaned_date.year, [0, 0])
                bucket[0] += 1
            if loan.returned_date:
                bucket = years.setdefault(loan.returned_date.year, [0, 0])
                bucket[1] += 1
        books = [LoanStatisticsBook(book_id, book.title, book.author, count) for book_id, (book, count) in book_counts.items()]
        books.sort(key=lambda item: (-item.loans, item.title.casefold(), str(item.book_id)))
        return LoanStatistics(
            active=sum(loan.state == "ACTIVE" for loan, _ in rows),
            overdue=sum(is_overdue(_period(loan)) for loan, _ in rows),
            completed=sum(loan.state == "RETURNED" for loan, _ in rows),
            unknown_loan_dates=sum(loan.loaned_date is None for loan, _ in rows),
            unknown_return_dates=sum(loan.state == "RETURNED" and loan.returned_date is None for loan, _ in rows),
            books=books,
            years=[LoanStatisticsYear(year, values[0], values[1]) for year, values in sorted(years.items(), reverse=True)],
        )

    def start(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        loaned_to: str,
        notes: str | None,
        loaned_date: date | None,
        expected_return_date: date | None,
    ) -> Loan:
        self._owner(library_id, actor_user_id)
        self._book(library_id, book_id, lock=True)
        if self._repository.active(library_id=library_id, book_id=book_id):
            raise LoanConflictError("This physical copy is already on loan.")
        record = Loan(
            library_id=library_id,
            book_id=book_id,
            state="ACTIVE",
            loaned_to=self._borrower(loaned_to),
            notes=self._notes(notes),
            loaned_date=loaned_date,
            expected_return_date=expected_return_date,
        )
        self._validate(record)
        self._repository.add(record)
        return self._save(record, actor_user_id, "loan.started")

    def return_active(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        returned_date: date | None,
    ) -> Loan:
        self._owner(library_id, actor_user_id)
        self._book(library_id, book_id, lock=True)
        record = self._repository.active(library_id=library_id, book_id=book_id)
        if record is None:
            raise LoanNotFoundError
        previous = (record.state, record.returned_date, record.updated_at)
        record.state = "RETURNED"
        record.returned_date = returned_date
        record.updated_at = datetime.now(UTC)
        try:
            self._validate(record)
        except LoanValidationError:
            record.state, record.returned_date, record.updated_at = previous
            raise
        return self._save(record, actor_user_id, "loan.returned")

    def cancel_active(
        self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID
    ) -> None:
        self._owner(library_id, actor_user_id)
        self._book(library_id, book_id, lock=True)
        record = self._repository.active(library_id=library_id, book_id=book_id)
        if record is None:
            raise LoanNotFoundError
        self._repository.delete(record)
        self._audit_commit(record, actor_user_id, "loan.cancelled")

    def add_historical(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        loaned_to: str,
        notes: str | None,
        loaned_date: date | None,
        expected_return_date: date | None,
        returned_date: date | None,
    ) -> Loan:
        self._owner(library_id, actor_user_id)
        self._book(library_id, book_id, lock=True)
        record = Loan(
            library_id=library_id,
            book_id=book_id,
            state="RETURNED",
            loaned_to=self._borrower(loaned_to),
            notes=self._notes(notes),
            loaned_date=loaned_date,
            expected_return_date=expected_return_date,
            returned_date=returned_date,
        )
        self._validate(record)
        self._repository.add(record)
        return self._save(record, actor_user_id, "loan.historical_added")

    def edit_historical(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        loan_id: UUID,
        actor_user_id: UUID,
        loaned_to: str,
        notes: str | None,
        loaned_date: date | None,
        expected_return_date: date | None,
        returned_date: date | None,
    ) -> Loan:
        record = self._returned(
            library_id, book_id, loan_id, actor_user_id, lock=True
        )
        previous = (
            record.loaned_to,
            record.notes,
            record.loaned_date,
            record.expected_return_date,
            record.returned_date,
            record.updated_at,
        )
        record.loaned_to = self._borrower(loaned_to)
        record.notes = self._notes(notes)
        record.loaned_date = loaned_date
        record.expected_return_date = expected_return_date
        record.returned_date = returned_date
        record.updated_at = datetime.now(UTC)
        try:
            self._validate(record)
        except LoanValidationError:
            (
                record.loaned_to,
                record.notes,
                record.loaned_date,
                record.expected_return_date,
                record.returned_date,
                record.updated_at,
            ) = previous
            raise
        return self._save(record, actor_user_id, "loan.historical_edited")

    def delete_historical(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        loan_id: UUID,
        actor_user_id: UUID,
    ) -> None:
        record = self._returned(
            library_id, book_id, loan_id, actor_user_id, lock=True
        )
        self._repository.delete(record)
        self._audit_commit(record, actor_user_id, "loan.historical_deleted")

    def _returned(
        self, library_id, book_id, loan_id, actor_user_id, *, lock: bool
    ) -> Loan:
        self._owner(library_id, actor_user_id)
        self._book(library_id, book_id, lock=lock)
        record = self._repository.loan(
            library_id=library_id, book_id=book_id, loan_id=loan_id
        )
        if record is None or record.state != "RETURNED":
            raise LoanNotFoundError
        return record

    @staticmethod
    def _borrower(value: str) -> str:
        try:
            return normalize_loaned_to(value)
        except LoanRuleViolation as exc:
            raise LoanValidationError(str(exc)) from exc

    @staticmethod
    def _notes(value: str | None) -> str | None:
        try:
            return normalize_notes(value)
        except LoanRuleViolation as exc:
            raise LoanValidationError(str(exc)) from exc

    @staticmethod
    def _validate(record: Loan) -> None:
        try:
            validate_loan(_period(record))
        except LoanRuleViolation as exc:
            raise LoanValidationError(str(exc)) from exc

    @staticmethod
    def _ordered(records: list[Loan]) -> list[Loan]:
        periods = order_loan_history(
            [_period(record, index) for index, record in enumerate(records)]
        )
        remaining = list(records)
        ordered: list[Loan] = []
        for period in periods:
            match = next(
                record
                for record in remaining
                if record.state == period.state.value
                and record.loaned_to == period.loaned_to
                and record.loaned_date == period.loaned_date
                and record.expected_return_date == period.expected_return_date
                and record.returned_date == period.returned_date
                and record.notes == period.notes
            )
            remaining.remove(match)
            ordered.append(match)
        return ordered

    @staticmethod
    def _viewer_item(record: Loan) -> ViewerLoanItem:
        return ViewerLoanItem(
            record.id,
            record.book_id,
            record.state,
            record.loaned_date,
            record.expected_return_date,
            record.returned_date,
            record.created_at,
            record.updated_at,
            is_overdue(_period(record)),
        )

    @classmethod
    def _owner_item(cls, record: Loan) -> OwnerLoanItem:
        public = cls._viewer_item(record)
        return OwnerLoanItem(
            **public.__dict__, loaned_to=record.loaned_to, notes=record.notes
        )

    def _save(self, record: Loan, actor_user_id: UUID, event_type: str) -> Loan:
        try:
            self._repository.flush()
            self._repository.audit(
                library_id=record.library_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                book_id=record.book_id,
                loan_id=record.id,
            )
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise LoanConflictError(
                "The loan changed concurrently; reload and retry."
            ) from exc
        return record

    def _audit_commit(
        self, record: Loan, actor_user_id: UUID, event_type: str
    ) -> None:
        self._repository.audit(
            library_id=record.library_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            book_id=record.book_id,
            loan_id=record.id,
        )
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise LoanConflictError(
                "The loan changed concurrently; reload and retry."
            ) from exc
