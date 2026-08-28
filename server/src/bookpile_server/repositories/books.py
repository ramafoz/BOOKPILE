from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from ..models import Book


def catalogue_query(library_id: UUID) -> Select[tuple[Book]]:
    """Build a catalogue query that can never be unscoped."""

    return (
        select(Book)
        .where(Book.library_id == library_id)
        .order_by(Book.title, Book.author, Book.id)
    )


class BookRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_library(self, library_id: UUID) -> list[Book]:
        return list(self._session.scalars(catalogue_query(library_id)))

