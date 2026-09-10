from dataclasses import dataclass
from datetime import UTC, date, datetime
from statistics import median
from uuid import UUID
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError

from ..models import Book, PersonalBookRecord, ReadingSession
from ..repositories.readings import ReadingRepository
from .reading_domain import (
    ReadingPeriod,
    ReadingRuleViolation,
    ReadingState,
    SessionState,
    derive_reading_state,
    order_history,
    validate_history,
)


class ReadingNotFoundError(Exception):
    pass


class ReadingAccessError(Exception):
    pass


class ReadingValidationError(Exception):
    pass


class ReadingConflictError(Exception):
    pass


@dataclass(frozen=True)
class ReadingProjection:
    user_id: UUID
    state: ReadingState
    sessions: list[ReadingSession]
    active_reader_present: bool
    writable: bool


@dataclass(frozen=True)
class ReadingCatalogueItem:
    book_id: UUID
    state: ReadingState
    active_reader_present: bool
    goodreads_url: str | None
    started_date: date | None
    finished_date: date | None
    dates_unknown: bool


@dataclass(frozen=True)
class ReadingCatalogueOverview:
    user_id: UUID
    writable: bool
    pending: int
    reading: int
    rereading: int
    read: int
    items: list[ReadingCatalogueItem]


@dataclass(frozen=True)
class ReadingStatisticsBook:
    book_id: UUID
    title: str
    author: str
    reading_events: int
    pages_read: int
    reading_days: int
    average_pages_per_day: float | None
    latest_finished_date: date | None


@dataclass(frozen=True)
class ReadingStatisticsYear:
    year: int
    reading_events: int
    books_read: int
    pages_read: int


@dataclass(frozen=True)
class ReadingDurationStatistic:
    average_days: float | None
    median_days: float | None
    sample_size: int
    excluded: int


@dataclass(frozen=True)
class ReadingStatistics:
    user_id: UUID
    total_catalogue_books: int
    unique_books_read: int
    completed_readings: int
    dated_readings: int
    rereadings: int
    pages_read: int
    average_pages_per_day: float | None
    median_pages_per_day: float | None
    pages_per_week: float | None
    pages_per_month: float | None
    active_readings: int
    pending_duration: ReadingDurationStatistic
    reading_duration: ReadingDurationStatistic
    books: list[ReadingStatisticsBook]
    years: list[ReadingStatisticsYear]


def _period(session: ReadingSession, order: int) -> ReadingPeriod:
    return ReadingPeriod(
        state=SessionState(session.state),
        started_date=session.started_date,
        finished_date=session.finished_date,
        dates_unknown=session.dates_unknown,
        creation_order=order,
    )


class ReadingService:
    def __init__(self, repository: ReadingRepository) -> None:
        self._repository = repository

    def _member(self, library_id: UUID, user_id: UUID):
        membership = self._repository.membership(
            library_id=library_id, user_id=user_id
        )
        if membership is None:
            raise ReadingNotFoundError
        return membership

    def _read_access(
        self, *, library_id: UUID, actor_user_id: UUID, perspective_user_id: UUID
    ) -> None:
        self._member(library_id, actor_user_id)
        target = self._member(library_id, perspective_user_id)
        if target.role != "OWNER":
            raise ReadingNotFoundError

    def require_perspective(
        self, *, library_id: UUID, actor_user_id: UUID, perspective_user_id: UUID
    ) -> None:
        """Validate a selected Owner before another read projection uses it."""
        self._read_access(
            library_id=library_id,
            actor_user_id=actor_user_id,
            perspective_user_id=perspective_user_id,
        )

    def _write_access(self, *, library_id: UUID, actor_user_id: UUID) -> None:
        membership = self._member(library_id, actor_user_id)
        if membership.role != "OWNER":
            raise ReadingAccessError("Only an Owner can change personal reading data.")

    def _book(self, library_id: UUID, book_id: UUID, *, lock: bool = False):
        book = (
            self._repository.lock_book(library_id=library_id, book_id=book_id)
            if lock
            else self._repository.book(library_id=library_id, book_id=book_id)
        )
        if book is None:
            raise ReadingNotFoundError
        return book

    def _validated(self, sessions: list[ReadingSession]) -> list[ReadingSession]:
        try:
            ordered_periods = validate_history(
                [_period(session, index) for index, session in enumerate(sessions)]
            )
        except ReadingRuleViolation as exc:
            raise ReadingValidationError(str(exc)) from exc
        # Reconstruct by stable values; IDs are not part of the pure period.
        remaining = list(sessions)
        result: list[ReadingSession] = []
        for period in ordered_periods:
            match = next(
                item
                for item in remaining
                if item.state == period.state.value
                and item.started_date == period.started_date
                and item.finished_date == period.finished_date
                and item.dates_unknown == period.dates_unknown
            )
            remaining.remove(match)
            result.append(match)
        return result

    def projection(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        perspective_user_id: UUID,
    ) -> ReadingProjection:
        self._read_access(
            library_id=library_id,
            actor_user_id=actor_user_id,
            perspective_user_id=perspective_user_id,
        )
        self._book(library_id, book_id)
        sessions = self._validated(
            self._repository.sessions(
                library_id=library_id,
                book_id=book_id,
                user_id=perspective_user_id,
            )
        )
        state = derive_reading_state(
            [_period(session, index) for index, session in enumerate(sessions)]
        )
        return ReadingProjection(
            user_id=perspective_user_id,
            state=state,
            sessions=sessions,
            active_reader_present=self._repository.active_for_book(
                library_id=library_id, book_id=book_id
            )
            is not None,
            writable=actor_user_id == perspective_user_id
            and self._member(library_id, actor_user_id).role == "OWNER",
        )

    def catalogue_overview(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        perspective_user_id: UUID,
    ) -> ReadingCatalogueOverview:
        self._read_access(
            library_id=library_id,
            actor_user_id=actor_user_id,
            perspective_user_id=perspective_user_id,
        )
        book_ids = self._repository.library_book_ids(library_id=library_id)
        grouped: dict[UUID, list[ReadingSession]] = {book_id: [] for book_id in book_ids}
        for session in self._repository.library_sessions(
            library_id=library_id, user_id=perspective_user_id
        ):
            grouped.setdefault(session.book_id, []).append(session)
        active_books = self._repository.active_book_ids(library_id=library_id)
        review_by_book = {
            record.book_id: record.goodreads_url
            for record in self._repository.personal_records(
                library_id=library_id, user_id=perspective_user_id
            )
        }
        states: dict[ReadingState, int] = {state: 0 for state in ReadingState}
        items: list[ReadingCatalogueItem] = []
        for book_id in book_ids:
            sessions = self._validated(grouped.get(book_id, []))
            state = derive_reading_state(
                [_period(session, index) for index, session in enumerate(sessions)]
            )
            states[state] += 1
            projected = next((item for item in reversed(sessions) if item.state == "ACTIVE"), None)
            if projected is None:
                projected = next((item for item in reversed(sessions) if item.state == "COMPLETED"), None)
            items.append(
                ReadingCatalogueItem(
                    book_id=book_id,
                    state=state,
                    active_reader_present=book_id in active_books,
                    goodreads_url=review_by_book.get(book_id),
                    started_date=projected.started_date if projected else None,
                    finished_date=projected.finished_date if projected else None,
                    dates_unknown=projected.dates_unknown if projected else False,
                )
            )
        return ReadingCatalogueOverview(
            user_id=perspective_user_id,
            writable=actor_user_id == perspective_user_id
            and self._member(library_id, actor_user_id).role == "OWNER",
            pending=states[ReadingState.PENDING],
            reading=states[ReadingState.READING],
            rereading=states[ReadingState.REREADING],
            read=states[ReadingState.READ],
            items=items,
        )

    def statistics(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        perspective_user_id: UUID,
        language: str | None = None,
        genre: str | None = None,
        publisher: str | None = None,
        reading_year: int | None = None,
    ) -> ReadingStatistics:
        self._read_access(
            library_id=library_id,
            actor_user_id=actor_user_id,
            perspective_user_id=perspective_user_id,
        )
        books = [
            book for book in self._repository.library_books(library_id=library_id)
            if self._statistics_book_matches(book, language, genre, publisher)
        ]
        by_book: dict[UUID, list[ReadingSession]] = {book.id: [] for book in books}
        for session in self._repository.library_sessions(
            library_id=library_id, user_id=perspective_user_id
        ):
            if session.book_id in by_book:
                by_book[session.book_id].append(session)

        result_books: list[ReadingStatisticsBook] = []
        yearly: dict[int, dict[str, object]] = {}
        all_rates: list[float] = []
        pending_days: list[int] = []
        reading_days: list[int] = []
        pending_excluded = reading_excluded = 0
        timeline_dates: list[date] = []
        total_events = dated_events = rereadings = pages_read = active_readings = 0
        unique_books_read = 0
        for book in books:
            sessions = self._validated(by_book[book.id])
            completed_all = [item for item in sessions if item.state == "COMPLETED"]
            active = [item for item in sessions if item.state == "ACTIVE"]
            active_readings += len(active)
            first_started = next((item.started_date for item in sessions if item.started_date), None)
            if sessions:
                if book.acquisition_date and first_started:
                    pending_days.append(max(1, (first_started - book.acquisition_date).days + 1))
                else:
                    pending_excluded += 1
            completed = [
                item for item in completed_all
                if reading_year is None
                or (item.finished_date is not None and item.finished_date.year == reading_year)
            ]
            if completed:
                unique_books_read += 1
            total_events += len(completed)
            rereadings += max(0, len(completed) - (1 if completed_all and completed_all[0] in completed else 0))
            book_pages = 0
            book_reading_days: list[int] = []
            for session in completed:
                if session.dates_unknown or session.finished_date is None:
                    reading_excluded += 1
                    continue
                dated_events += 1
                pages = book.page_count or 0
                book_pages += pages
                if book.page_count and session.started_date:
                    days = (session.finished_date - session.started_date).days + 1
                    measured_days = max(1, days)
                    reading_days.append(measured_days)
                    book_reading_days.append(measured_days)
                    rate = book.page_count / measured_days
                    all_rates.append(rate)
                    timeline_dates.extend([session.started_date, session.finished_date])
                elif session.started_date:
                    reading_days.append(max(1, (session.finished_date - session.started_date).days + 1))
                bucket = yearly.setdefault(
                    session.finished_date.year,
                    {"events": 0, "books": set(), "pages": 0},
                )
                bucket["events"] = int(bucket["events"]) + 1
                cast_books = bucket["books"]
                if isinstance(cast_books, set):
                    cast_books.add(book.id)
                bucket["pages"] = int(bucket["pages"]) + pages
            pages_read += book_pages
            if completed:
                result_books.append(ReadingStatisticsBook(
                    book_id=book.id,
                    title=book.title,
                    author=book.author,
                    reading_events=len(completed),
                    pages_read=book_pages,
                    reading_days=sum(book_reading_days),
                    average_pages_per_day=(
                        book.page_count * len(book_reading_days) / sum(book_reading_days)
                        if book.page_count and book_reading_days else None
                    ),
                    latest_finished_date=max(
                        (item.finished_date for item in completed if item.finished_date),
                        default=None,
                    ),
                ))
        timeline_days = ((max(timeline_dates) - min(timeline_dates)).days + 1) if timeline_dates else 0
        duration_summary = lambda values, excluded: ReadingDurationStatistic(
            average_days=(sum(values) / len(values)) if values else None,
            median_days=float(median(values)) if values else None,
            sample_size=len(values),
            excluded=excluded,
        )
        return ReadingStatistics(
            user_id=perspective_user_id,
            total_catalogue_books=len(books),
            unique_books_read=unique_books_read,
            completed_readings=total_events,
            dated_readings=dated_events,
            rereadings=rereadings,
            pages_read=pages_read,
            average_pages_per_day=(sum(all_rates) / len(all_rates)) if all_rates else None,
            median_pages_per_day=float(median(all_rates)) if all_rates else None,
            pages_per_week=(pages_read / timeline_days * 7) if timeline_days else None,
            pages_per_month=(pages_read / timeline_days * (365.2425 / 12)) if timeline_days else None,
            active_readings=active_readings,
            pending_duration=duration_summary(pending_days, pending_excluded),
            reading_duration=duration_summary(reading_days, reading_excluded),
            books=sorted(result_books, key=lambda item: ((item.latest_finished_date or date.min), item.title), reverse=True),
            years=[ReadingStatisticsYear(
                year=year,
                reading_events=int(values["events"]),
                books_read=len(values["books"]) if isinstance(values["books"], set) else 0,
                pages_read=int(values["pages"]),
            ) for year, values in sorted(yearly.items(), reverse=True)],
        )

    @staticmethod
    def _statistics_book_matches(
        book: Book,
        language: str | None,
        genre: str | None,
        publisher: str | None,
    ) -> bool:
        if language and (book.language or "").casefold() != language.casefold():
            return False
        if publisher and (book.publisher or "").casefold() != publisher.casefold():
            return False
        if genre:
            genres = {(item.strip()).casefold() for item in (book.genre_text or "").split(",") if item.strip()}
            if genre.casefold() not in genres:
                return False
        return True

    def start(
        self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID, started: date
    ) -> ReadingSession:
        self._write_access(library_id=library_id, actor_user_id=actor_user_id)
        self._book(library_id, book_id, lock=True)
        if self._repository.active_loan_for_book(
            library_id=library_id, book_id=book_id
        ):
            raise ReadingConflictError(
                "This physical copy is on loan and cannot start a reading."
            )
        if self._repository.active_for_book(library_id=library_id, book_id=book_id):
            raise ReadingConflictError("This physical copy is already being read.")
        sessions = self._repository.sessions(
            library_id=library_id, book_id=book_id, user_id=actor_user_id
        )
        record = ReadingSession(
            library_id=library_id,
            book_id=book_id,
            user_id=actor_user_id,
            state="ACTIVE",
            started_date=started,
            dates_unknown=False,
        )
        self._validate_candidate(sessions + [record])
        self._repository.add(record)
        return self._save(record, library_id, actor_user_id, "reading.started")

    def finish(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
        finished: date,
    ) -> ReadingSession:
        record = self._owned_session(
            library_id, book_id, session_id, actor_user_id, active=True
        )
        sessions = self._repository.sessions(
            library_id=library_id, book_id=book_id, user_id=actor_user_id
        )
        previous = (record.state, record.finished_date, record.updated_at)
        record.state = "COMPLETED"
        record.finished_date = finished
        record.updated_at = datetime.now(UTC)
        try:
            self._validate_candidate(sessions)
        except ReadingValidationError:
            record.state, record.finished_date, record.updated_at = previous
            raise
        return self._save(record, library_id, actor_user_id, "reading.finished")

    def cancel(
        self, *, library_id: UUID, book_id: UUID, session_id: UUID, actor_user_id: UUID
    ) -> None:
        record = self._owned_session(
            library_id, book_id, session_id, actor_user_id, active=True
        )
        self._repository.delete(record)
        self._audit_and_commit(
            library_id, actor_user_id, "reading.cancelled", {"session_id": str(session_id)}
        )

    def add_historical(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        started: date | None,
        finished: date | None,
        dates_unknown: bool,
    ) -> ReadingSession:
        self._write_access(library_id=library_id, actor_user_id=actor_user_id)
        self._book(library_id, book_id, lock=True)
        sessions = self._repository.sessions(
            library_id=library_id, book_id=book_id, user_id=actor_user_id
        )
        record = ReadingSession(
            library_id=library_id,
            book_id=book_id,
            user_id=actor_user_id,
            state="COMPLETED",
            started_date=started,
            finished_date=finished,
            dates_unknown=dates_unknown,
        )
        self._validate_candidate(sessions + [record])
        self._repository.add(record)
        return self._save(record, library_id, actor_user_id, "reading.historical_added")

    def edit_completed(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        session_id: UUID,
        actor_user_id: UUID,
        started: date | None,
        finished: date | None,
        dates_unknown: bool,
    ) -> ReadingSession:
        record = self._owned_session(
            library_id, book_id, session_id, actor_user_id, active=False
        )
        sessions = self._repository.sessions(
            library_id=library_id, book_id=book_id, user_id=actor_user_id
        )
        previous = (
            record.started_date,
            record.finished_date,
            record.dates_unknown,
            record.updated_at,
        )
        record.started_date = started
        record.finished_date = finished
        record.dates_unknown = dates_unknown
        record.updated_at = datetime.now(UTC)
        try:
            self._validate_candidate(sessions)
        except ReadingValidationError:
            (
                record.started_date,
                record.finished_date,
                record.dates_unknown,
                record.updated_at,
            ) = previous
            raise
        return self._save(record, library_id, actor_user_id, "reading.edited")

    def delete_completed(
        self, *, library_id: UUID, book_id: UUID, session_id: UUID, actor_user_id: UUID
    ) -> None:
        record = self._owned_session(
            library_id, book_id, session_id, actor_user_id, active=False
        )
        self._repository.delete(record)
        self._audit_and_commit(
            library_id, actor_user_id, "reading.deleted", {"session_id": str(session_id)}
        )

    def set_goodreads(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        url: str | None,
    ) -> PersonalBookRecord | None:
        self._write_access(library_id=library_id, actor_user_id=actor_user_id)
        self._book(library_id, book_id)
        cleaned = url.strip() if url else None
        if cleaned:
            parsed = urlparse(cleaned)
            host = (parsed.hostname or "").lower()
            if parsed.scheme != "https" or not (
                host == "goodreads.com" or host.endswith(".goodreads.com")
            ):
                raise ReadingValidationError("Use an HTTPS Goodreads URL.")
        record = self._repository.personal_record(
            library_id=library_id, book_id=book_id, user_id=actor_user_id
        )
        if not cleaned:
            if record is not None:
                self._repository.delete(record)
        elif record is None:
            record = PersonalBookRecord(
                library_id=library_id,
                book_id=book_id,
                user_id=actor_user_id,
                goodreads_url=cleaned,
            )
            self._repository.add(record)
        else:
            record.goodreads_url = cleaned
            record.updated_at = datetime.now(UTC)
        self._audit_and_commit(
            library_id, actor_user_id, "personal_book.goodreads_changed", {"book_id": str(book_id)}
        )
        return record if cleaned else None

    def reviews(self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID):
        self._member(library_id, actor_user_id)
        self._book(library_id, book_id)
        return self._repository.reviews(library_id=library_id, book_id=book_id)

    def _owned_session(self, library_id, book_id, session_id, actor_user_id, *, active):
        self._write_access(library_id=library_id, actor_user_id=actor_user_id)
        self._book(library_id, book_id, lock=True)
        record = self._repository.session(
            library_id=library_id, book_id=book_id, session_id=session_id
        )
        expected = "ACTIVE" if active else "COMPLETED"
        if record is None or record.user_id != actor_user_id or record.state != expected:
            raise ReadingNotFoundError
        return record

    def _validate_candidate(self, sessions: list[ReadingSession]) -> None:
        try:
            validate_history([_period(item, index) for index, item in enumerate(sessions)])
        except ReadingRuleViolation as exc:
            raise ReadingValidationError(str(exc)) from exc

    def _save(self, record, library_id, actor_user_id, event_type):
        try:
            self._repository.flush()
            self._repository.audit(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                details={
                    "book_id": str(record.book_id),
                    "session_id": str(record.id),
                },
            )
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise ReadingConflictError("The reading changed concurrently; reload and retry.") from exc
        return record

    def _audit_and_commit(self, library_id, actor_user_id, event_type, details):
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            details=details,
        )
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise ReadingConflictError(
                "The reading data changed concurrently; reload and retry."
            ) from exc

    def username(self, user_id: UUID) -> str:
        return self._repository.username(user_id) or "Unknown user"
