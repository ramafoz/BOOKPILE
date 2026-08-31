from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from ..isbn import InvalidISBN, normalize_isbn
from ..models import Book, BookContributor, ContributorRole
from ..repositories.books import BookRepository
from ..schemas import BookWrite


class CatalogueNotFoundError(Exception):
    pass


class CatalogueValidationError(Exception):
    pass


class CatalogueConflictError(Exception):
    pass


@dataclass(frozen=True)
class BookRecord:
    book: Book
    contributors: list[tuple[BookContributor, ContributorRole]]

    @property
    def display_author(self) -> str:
        authors = [
            contributor.name
            for contributor, _ in self.contributors
            if contributor.role_code == "AUTHOR"
        ]
        if len(authors) == 2:
            return " & ".join(authors)
        if len(authors) > 2:
            return "Multiple authors"
        return self.book.author


@dataclass(frozen=True)
class CataloguePage:
    records: list[BookRecord]
    total: int
    limit: int
    offset: int


@dataclass(frozen=True)
class MetadataOptions:
    languages: list[str]
    original_languages: list[str]
    publishers: list[str]
    genres: list[str]
    series_names: list[str]
    roles: list[ContributorRole]


class CatalogueService:
    def __init__(self, books: BookRepository) -> None:
        self._books = books

    def _validated_filters(self, filters: dict[str, object]) -> dict[str, object]:
        page_min = filters.get("page_min")
        page_max = filters.get("page_max")
        year_min = filters.get("year_min")
        year_max = filters.get("year_max")
        if page_min is not None and page_max is not None and page_min > page_max:
            raise CatalogueValidationError(
                "Minimum pages must be less than or equal to maximum pages."
            )
        if year_min is not None and year_max is not None and year_min > year_max:
            raise CatalogueValidationError(
                "Minimum year must be less than or equal to maximum year."
            )
        isbn = filters.get("isbn")
        if isinstance(isbn, str) and isbn.strip():
            try:
                filters["isbn"] = normalize_isbn(isbn)
            except InvalidISBN as exc:
                raise CatalogueValidationError(str(exc)) from exc
        else:
            filters["isbn"] = None
        return filters

    def list_books(
        self,
        library_id: UUID,
        *,
        limit: int,
        offset: int,
        sort_by: str,
        sort_order: str,
        **filters: object,
    ) -> CataloguePage:
        filters = self._validated_filters(filters)
        books = self._books.list_for_library(
            library_id,
            limit=limit,
            offset=offset,
            sort_by=sort_by,
            sort_order=sort_order,
            **filters,
        )
        contributors = self._books.contributors_for_books(
            library_id, [book.id for book in books]
        )
        return CataloguePage(
            records=[
                BookRecord(book=book, contributors=contributors[book.id])
                for book in books
            ],
            total=self._books.count_for_library(library_id, **filters),
            limit=limit,
            offset=offset,
        )

    def get_book(self, library_id: UUID, book_id: UUID) -> BookRecord:
        book = self._books.find_for_library(library_id, book_id)
        if book is None:
            raise CatalogueNotFoundError
        contributors = self._books.contributors_for_books(library_id, [book.id])
        return BookRecord(book=book, contributors=contributors[book.id])

    def metadata_options(self, library_id: UUID) -> MetadataOptions:
        return MetadataOptions(
            languages=self._books.distinct_values(library_id, Book.language),
            original_languages=self._books.distinct_values(
                library_id, Book.original_language
            ),
            publishers=self._books.distinct_values(library_id, Book.publisher),
            genres=self._books.genre_values(library_id),
            series_names=self._books.distinct_values(library_id, Book.series_name),
            roles=self._books.list_roles(active_only=True),
        )

    def create_book(
        self, *, library_id: UUID, actor_user_id: UUID, payload: BookWrite
    ) -> BookRecord:
        roles = self._validated_roles(payload)
        values = self._book_values(payload)
        book = Book(library_id=library_id, **values)
        self._books.add(book)
        try:
            self._books.flush()
            self._books.replace_contributors(
                library_id,
                book.id,
                self._contributors(library_id, book.id, payload, roles),
            )
            self._books.audit(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type="book_created",
                details={"book_id": str(book.id), "title": book.title},
            )
            self._books.commit()
        except IntegrityError as exc:
            self._books.rollback()
            raise CatalogueConflictError(
                "The book could not be saved because its data conflicts with the catalogue."
            ) from exc
        return self.get_book(library_id, book.id)

    def update_book(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        payload: BookWrite,
    ) -> BookRecord:
        book = self._books.find_for_library(library_id, book_id)
        if book is None:
            raise CatalogueNotFoundError
        roles = self._validated_roles(payload)
        old_title = book.title
        for field, value in self._book_values(payload).items():
            setattr(book, field, value)
        book.updated_at = datetime.now(UTC)
        try:
            self._books.replace_contributors(
                library_id,
                book.id,
                self._contributors(library_id, book.id, payload, roles),
            )
            self._books.flush()
            self._books.audit(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type="book_updated",
                details={
                    "book_id": str(book.id),
                    "title": book.title,
                    "previous_title": old_title,
                },
            )
            self._books.commit()
        except IntegrityError as exc:
            self._books.rollback()
            raise CatalogueConflictError(
                "The book could not be updated because its data conflicts with the catalogue."
            ) from exc
        return self.get_book(library_id, book.id)

    def delete_book(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        confirmation_title: str,
    ) -> None:
        book = self._books.find_for_library(library_id, book_id)
        if book is None:
            raise CatalogueNotFoundError
        if confirmation_title.strip() != book.title:
            raise CatalogueValidationError(
                "Enter the exact book title to confirm permanent deletion."
            )
        details = {"book_id": str(book.id), "title": book.title}
        self._books.delete(book)
        self._books.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="book_deleted",
            details=details,
        )
        try:
            self._books.commit()
        except IntegrityError as exc:
            self._books.rollback()
            raise CatalogueConflictError(
                "This book cannot be deleted while other library records depend on it."
            ) from exc

    def _validated_roles(self, payload: BookWrite) -> dict[str, ContributorRole]:
        roles = {role.code: role for role in self._books.list_roles()}
        for contributor in payload.contributors:
            role = roles.get(contributor.role_code)
            if role is None or not role.is_active:
                raise CatalogueValidationError(
                    f"Contributor role {contributor.role_code} is unavailable."
                )
        return roles

    @staticmethod
    def _book_values(payload: BookWrite) -> dict[str, object]:
        values = payload.model_dump(exclude={"contributors"})
        return values

    @staticmethod
    def _contributors(
        library_id: UUID,
        book_id: UUID,
        payload: BookWrite,
        roles: dict[str, ContributorRole],
    ) -> list[BookContributor]:
        positions: Counter[str] = Counter()
        result: list[BookContributor] = []
        for item in payload.contributors:
            positions[item.role_code] += 1
            result.append(
                BookContributor(
                    library_id=library_id,
                    book_id=book_id,
                    role_code=roles[item.role_code].code,
                    position=positions[item.role_code],
                    name=item.name,
                )
            )
        return result
