from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import Session

from ..models import Book


def catalogue_filters(library_id: UUID, search: str | None) -> list[object]:
    filters: list[object] = [Book.library_id == library_id]
    if search:
        pattern = f"%{search.strip()}%"
        filters.append(or_(Book.title.ilike(pattern), Book.author.ilike(pattern)))
    return filters


def catalogue_query(
    library_id: UUID,
    *,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> Select[tuple[Book]]:
    """Build a catalogue query that can never be unscoped."""

    return (
        select(Book)
        .where(*catalogue_filters(library_id, search))
        .order_by(Book.title, Book.author, Book.id)
        .limit(limit)
        .offset(offset)
    )


class BookRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_library(
        self,
        library_id: UUID,
        *,
        search: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Book]:
        return list(
            self._session.scalars(
                catalogue_query(
                    library_id,
                    search=search,
                    limit=limit,
                    offset=offset,
                )
            )
        )

    def count_for_library(
        self,
        library_id: UUID,
        *,
        search: str | None = None,
    ) -> int:
        statement = (
            select(func.count())
            .select_from(Book)
            .where(*catalogue_filters(library_id, search))
        )
        return self._session.scalar(statement) or 0

