from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import Select, and_, delete, exists, func, or_, select
from sqlalchemy.orm import Session

from ..models import Book, BookContributor, ContributorRole, LibraryAuditEvent


def _exact_values(column: object, values: Sequence[str]) -> object | None:
    cleaned = [value.strip().lower() for value in values if value.strip()]
    return func.lower(column).in_(cleaned) if cleaned else None


def _genre_condition(genres: Sequence[str]) -> object | None:
    conditions: list[object] = []
    value = func.lower(Book.genre_text)
    for genre in (item.strip().lower() for item in genres if item.strip()):
        conditions.append(
            or_(
                value == genre,
                value.like(f"{genre}, %"),
                value.like(f"%, {genre}"),
                value.like(f"%, {genre}, %"),
            )
        )
    return or_(*conditions) if conditions else None


def catalogue_filters(
    library_id: UUID,
    *,
    search: str | None = None,
    isbn: str | None = None,
    languages: Sequence[str] = (),
    original_languages: Sequence[str] = (),
    translation_statuses: Sequence[str] = (),
    genres: Sequence[str] = (),
    publishers: Sequence[str] = (),
    fiction_categories: Sequence[str] = (),
    bindings: Sequence[str] = (),
    publication_types: Sequence[str] = (),
    series_names: Sequence[str] = (),
    series_state: str = "ANY",
    author_structure: str = "ANY",
    page_min: int | None = None,
    page_max: int | None = None,
    year_field: str = "current_ed_year",
    year_min: int | None = None,
    year_max: int | None = None,
) -> list[object]:
    filters: list[object] = [Book.library_id == library_id]
    if search and search.strip():
        pattern = f"%{search.strip()}%"
        contributor_match = exists(
            select(BookContributor.id).where(
                BookContributor.library_id == library_id,
                BookContributor.book_id == Book.id,
                BookContributor.name.ilike(pattern),
            )
        )
        filters.append(
            or_(
                Book.title.ilike(pattern),
                Book.author.ilike(pattern),
                Book.series_name.ilike(pattern),
                contributor_match,
            )
        )
    if isbn:
        filters.append(or_(Book.isbn_10 == isbn, Book.isbn_13 == isbn))
    for condition in (
        _exact_values(Book.language, languages),
        _exact_values(Book.original_language, original_languages),
        _exact_values(Book.translation_status, translation_statuses),
        _genre_condition(genres),
        _exact_values(Book.publisher, publishers),
        _exact_values(Book.fiction_category, fiction_categories),
        _exact_values(Book.binding, bindings),
        _exact_values(Book.publication_type, publication_types),
        _exact_values(Book.series_name, series_names),
    ):
        if condition is not None:
            filters.append(condition)
    if series_state == "YES":
        filters.append(and_(Book.series_name.is_not(None), Book.series_name != ""))
    elif series_state == "NO":
        filters.append(or_(Book.series_name.is_(None), Book.series_name == ""))
    structured_authors = (
        select(func.count(BookContributor.id))
        .where(
            BookContributor.library_id == library_id,
            BookContributor.book_id == Book.id,
            BookContributor.role_code == "AUTHOR",
        )
        .correlate(Book)
        .scalar_subquery()
    )
    if author_structure == "MULTIPLE":
        filters.append(or_(structured_authors >= 2, Book.author == "Multiple authors"))
    elif author_structure == "SINGLE":
        filters.append(and_(structured_authors < 2, Book.author != "Multiple authors"))
    if page_min is not None:
        filters.append(Book.page_count >= page_min)
    if page_max is not None:
        filters.append(Book.page_count <= page_max)
    year_column = (
        Book.original_publication_year
        if year_field == "original_publication_year"
        else Book.current_ed_year
    )
    if year_min is not None:
        filters.append(year_column >= year_min)
    if year_max is not None:
        filters.append(year_column <= year_max)
    return filters


SORT_COLUMNS = {
    "title": Book.title,
    "author": Book.author,
    "created_at": Book.created_at,
    "updated_at": Book.updated_at,
    "page_count": Book.page_count,
    "publisher": Book.publisher,
    "current_ed_year": Book.current_ed_year,
    "original_publication_year": Book.original_publication_year,
    "acquisition_date": Book.acquisition_date,
}


def catalogue_query(
    library_id: UUID,
    *,
    limit: int = 50,
    offset: int = 0,
    sort_by: str = "title",
    sort_order: str = "asc",
    **filters: object,
) -> Select[tuple[Book]]:
    column = SORT_COLUMNS.get(sort_by, Book.title)
    direction = column.desc() if sort_order == "desc" else column.asc()
    return (
        select(Book)
        .where(*catalogue_filters(library_id, **filters))
        .order_by(column.is_(None), direction, Book.title, Book.id)
        .limit(limit)
        .offset(offset)
    )


class BookRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_library(self, library_id: UUID, **options: object) -> list[Book]:
        return list(self._session.scalars(catalogue_query(library_id, **options)))

    def count_for_library(self, library_id: UUID, **filters: object) -> int:
        statement = (
            select(func.count())
            .select_from(Book)
            .where(*catalogue_filters(library_id, **filters))
        )
        return self._session.scalar(statement) or 0

    def find_for_library(self, library_id: UUID, book_id: UUID) -> Book | None:
        return self._session.scalar(
            select(Book).where(Book.library_id == library_id, Book.id == book_id)
        )

    def contributors_for_books(
        self, library_id: UUID, book_ids: Sequence[UUID]
    ) -> dict[UUID, list[tuple[BookContributor, ContributorRole]]]:
        result: dict[UUID, list[tuple[BookContributor, ContributorRole]]] = {
            book_id: [] for book_id in book_ids
        }
        if not book_ids:
            return result
        rows = self._session.execute(
            select(BookContributor, ContributorRole)
            .join(ContributorRole, ContributorRole.code == BookContributor.role_code)
            .where(
                BookContributor.library_id == library_id,
                BookContributor.book_id.in_(book_ids),
            )
            .order_by(
                BookContributor.book_id,
                ContributorRole.sort_order,
                BookContributor.position,
                BookContributor.id,
            )
        )
        for contributor, role in rows:
            result[contributor.book_id].append((contributor, role))
        return result

    def list_roles(self, *, active_only: bool = False) -> list[ContributorRole]:
        statement = select(ContributorRole)
        if active_only:
            statement = statement.where(ContributorRole.is_active.is_(True))
        return list(
            self._session.scalars(
                statement.order_by(ContributorRole.sort_order, ContributorRole.code)
            )
        )

    def distinct_values(self, library_id: UUID, column: object) -> list[str]:
        values = self._session.scalars(
            select(column)
            .where(
                Book.library_id == library_id,
                column.is_not(None),
                column != "",
            )
            .distinct()
        )
        # PostgreSQL requires every DISTINCT query's ORDER BY expression to
        # appear in the SELECT list. Sorting the small option vocabulary after
        # the library-scoped query is both portable and case-insensitive.
        return sorted(
            (value for value in values if value),
            key=str.casefold,
        )

    def genre_values(self, library_id: UUID) -> list[str]:
        values = self._session.scalars(
            select(Book.genre_text).where(
                Book.library_id == library_id, Book.genre_text.is_not(None)
            )
        )
        return sorted(
            {
                genre.strip()
                for value in values
                for genre in (value or "").split(",")
                if genre.strip()
            },
            key=str.casefold,
        )

    def add(self, book: Book) -> None:
        self._session.add(book)

    def replace_contributors(
        self, library_id: UUID, book_id: UUID, contributors: list[BookContributor]
    ) -> None:
        self._session.execute(
            delete(BookContributor).where(
                BookContributor.library_id == library_id,
                BookContributor.book_id == book_id,
            )
        )
        self._session.add_all(contributors)

    def delete(self, book: Book) -> None:
        self._session.delete(book)

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
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
