from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from ..config import Settings
from ..cover_images import ProcessedCover
from ..cover_storage import CoverStorage
from ..models import BookCover
from ..repositories.books import BookRepository
from ..repositories.covers import CoverRepository
from .catalogue import CatalogueConflictError, CatalogueNotFoundError


class CoverNotFoundError(Exception):
    pass


class CoverStorageError(Exception):
    pass


@dataclass(frozen=True)
class StoredCover:
    metadata: BookCover
    content: bytes


class CoverService:
    def __init__(self, covers: CoverRepository, books: BookRepository, storage: CoverStorage, settings: Settings) -> None:
        self._covers = covers
        self._books = books
        self._storage = storage
        self._settings = settings

    def get(self, library_id: UUID, book_id: UUID) -> StoredCover:
        if self._books.find_for_library(library_id, book_id) is None:
            raise CatalogueNotFoundError
        cover = self._covers.find(library_id, book_id)
        if cover is None:
            raise CoverNotFoundError
        try:
            return StoredCover(cover, self._storage.read(cover.object_key))
        except OSError as exc:
            raise CoverStorageError("The stored cover is temporarily unavailable.") from exc

    def replace(self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID, image: ProcessedCover) -> BookCover:
        book = self._books.find_for_library(library_id, book_id)
        if book is None:
            raise CatalogueNotFoundError
        old = self._covers.find(library_id, book_id)
        old_key = old.object_key if old else None
        object_key = f"covers/{uuid4().hex}.webp"
        try:
            self._storage.put(object_key, image.content)
        except OSError as exc:
            raise CoverStorageError("BOOKPILE could not store this cover.") from exc
        now = datetime.now(UTC)
        cover = old or BookCover(library_id=library_id, book_id=book_id)
        cover.object_key = object_key
        cover.media_type = "image/webp"
        cover.byte_size = len(image.content)
        cover.width_px = image.width_px
        cover.height_px = image.height_px
        cover.sha256 = image.sha256
        cover.uploaded_by_user_id = actor_user_id
        cover.updated_at = now
        if old is None:
            self._covers.add(cover)
        self._covers.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="cover_replaced" if old_key else "cover_uploaded",
            details={"book_id": str(book_id), "byte_size": cover.byte_size},
        )
        try:
            self._covers.commit()
        except IntegrityError as exc:
            self._covers.rollback()
            self._storage.delete(object_key)
            raise CatalogueConflictError("The cover metadata could not be saved.") from exc
        if old_key and old_key != object_key:
            try:
                self._storage.delete(old_key)
            except OSError:
                pass
        return cover

    def remove(self, *, library_id: UUID, book_id: UUID, actor_user_id: UUID) -> None:
        if self._books.find_for_library(library_id, book_id) is None:
            raise CatalogueNotFoundError
        cover = self._covers.find(library_id, book_id)
        if cover is None:
            raise CoverNotFoundError
        object_key = cover.object_key
        self._covers.delete(cover)
        self._covers.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="cover_removed",
            details={"book_id": str(book_id)},
        )
        self._covers.commit()
        try:
            self._storage.delete(object_key)
        except OSError:
            pass

    def object_key(self, library_id: UUID, book_id: UUID) -> str | None:
        cover = self._covers.find(library_id, book_id)
        return cover.object_key if cover else None

    def delete_object_after_book(self, object_key: str | None) -> None:
        if object_key:
            try:
                self._storage.delete(object_key)
            except OSError:
                pass
