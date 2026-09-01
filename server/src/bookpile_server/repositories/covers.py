from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import BookCover, LibraryAuditEvent


class CoverRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find(self, library_id: UUID, book_id: UUID) -> BookCover | None:
        return self._session.scalar(
            select(BookCover).where(
                BookCover.library_id == library_id, BookCover.book_id == book_id
            )
        )

    def add(self, cover: BookCover) -> None:
        self._session.add(cover)

    def delete(self, cover: BookCover) -> None:
        self._session.delete(cover)

    def audit(self, *, library_id: UUID, actor_user_id: UUID, event_type: str, details: dict[str, object]) -> None:
        self._session.add(LibraryAuditEvent(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type=event_type,
            details=details,
        ))

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
