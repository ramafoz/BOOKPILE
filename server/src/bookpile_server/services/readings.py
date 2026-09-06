from dataclasses import dataclass
from datetime import UTC, date, datetime
from uuid import UUID
from urllib.parse import urlparse

from sqlalchemy.exc import IntegrityError

from ..models import PersonalBookRecord, ReadingSession
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

    def start(
        self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID, started: date
    ) -> ReadingSession:
        self._write_access(library_id=library_id, actor_user_id=actor_user_id)
        self._book(library_id, book_id, lock=True)
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
