from uuid import UUID

from ..models import Book
from ..repositories.books import BookRepository


class CatalogueService:
    def __init__(self, books: BookRepository) -> None:
        self._books = books

    def list_books(self, library_id: UUID) -> list[Book]:
        return self._books.list_for_library(library_id)

