from uuid import UUID

from ..models import Book
from ..repositories.books import BookRepository


class CataloguePage:
    def __init__(
        self,
        *,
        books: list[Book],
        total: int,
        limit: int,
        offset: int,
    ) -> None:
        self.books = books
        self.total = total
        self.limit = limit
        self.offset = offset


class CatalogueService:
    def __init__(self, books: BookRepository) -> None:
        self._books = books

    def list_books(
        self,
        library_id: UUID,
        *,
        search: str | None,
        limit: int,
        offset: int,
    ) -> CataloguePage:
        return CataloguePage(
            books=self._books.list_for_library(
                library_id,
                search=search,
                limit=limit,
                offset=offset,
            ),
            total=self._books.count_for_library(library_id, search=search),
            limit=limit,
            offset=offset,
        )

