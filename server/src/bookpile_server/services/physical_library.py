from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from ..models import Book, Bookcase, Container, Shelf
from ..repositories.physical_library import PhysicalLibraryRepository
from ..schemas import (
    BookcaseWrite,
    BookPlacementWrite,
    ContainerUpdate,
    ContainerWrite,
    ShelfUpdate,
    ShelfWrite,
)


class PhysicalLibraryNotFoundError(Exception):
    pass


class PhysicalLibraryConflictError(Exception):
    pass


class PhysicalLibraryValidationError(Exception):
    pass


@dataclass(frozen=True)
class PhysicalHierarchy:
    bookcases: list[Bookcase]
    shelves: list[Shelf]
    containers: list[Container]
    book_counts: dict[UUID, int]
    books: list[Book]


class PhysicalLibraryService:
    def __init__(self, repository: PhysicalLibraryRepository) -> None:
        self._repository = repository

    def hierarchy(self, library_id: UUID) -> PhysicalHierarchy:
        return PhysicalHierarchy(
            bookcases=self._repository.list_bookcases(library_id),
            shelves=self._repository.list_shelves(library_id),
            containers=self._repository.list_containers(library_id),
            book_counts=self._repository.book_counts(library_id),
            books=self._repository.list_books(library_id),
        )

    def place_book(
        self,
        *,
        library_id: UUID,
        book_id: UUID,
        actor_user_id: UUID,
        payload: BookPlacementWrite,
    ) -> None:
        book = self._repository.find_book(library_id, book_id)
        if book is None:
            raise PhysicalLibraryNotFoundError("Book not found.")
        if (
            payload.container_id is not None
            and self._repository.find_container(library_id, payload.container_id)
            is None
        ):
            raise PhysicalLibraryNotFoundError("Destination container not found.")

        previous_container_id = book.container_id
        previous_position = book.position
        affected = {
            item
            for item in (previous_container_id, payload.container_id)
            if item is not None
        }
        positioned = self._repository.positioned_books(library_id, affected)
        ordered = {
            container_id: [item for item in items if item.id != book.id]
            for container_id, items in positioned.items()
        }

        if payload.container_id is not None:
            destination = ordered[payload.container_id]
            assert payload.position is not None
            if payload.position > len(destination) + 1:
                raise PhysicalLibraryValidationError(
                    f"Choose a position between 1 and {len(destination) + 1}. "
                    "Physical containers cannot contain gaps."
                )
            destination.insert(payload.position - 1, book)

        placements: dict[UUID, tuple[UUID | None, int | None]] = {}
        for container_id, items in ordered.items():
            for position, item in enumerate(items, start=1):
                placements[item.id] = (container_id, position)
        if payload.container_id is None:
            placements[book.id] = (None, None)

        self._repository.replace_placements(
            library_id=library_id,
            affected_containers=affected,
            placements=placements,
        )
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="book_placement_updated",
            details={
                "book_id": str(book.id),
                "previous_container_id": str(previous_container_id)
                if previous_container_id
                else None,
                "previous_position": previous_position,
                "container_id": str(payload.container_id)
                if payload.container_id
                else None,
                "position": payload.position,
            },
        )
        self._commit("The book could not be placed at that position.")
        # Placement updates are intentionally bulk operations so unique
        # positions can be vacated before they are reassigned. Refresh the
        # identity map before building the response in the same request.
        self._repository.expire_all()

    def create_bookcase(
        self, *, library_id: UUID, actor_user_id: UUID, payload: BookcaseWrite
    ) -> Bookcase:
        item = Bookcase(library_id=library_id, **payload.model_dump())
        return self._save_created(
            item,
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="bookcase_created",
            details=lambda: {"bookcase_id": str(item.id), "name": item.name},
            conflict="A bookcase with this name already exists in the library.",
        )

    def update_bookcase(
        self,
        *,
        library_id: UUID,
        bookcase_id: UUID,
        actor_user_id: UUID,
        payload: BookcaseWrite,
    ) -> Bookcase:
        item = self._repository.find_bookcase(library_id, bookcase_id)
        if item is None:
            raise PhysicalLibraryNotFoundError("Bookcase not found.")
        previous_name = item.name
        for field, value in payload.model_dump().items():
            setattr(item, field, value)
        item.updated_at = datetime.now(UTC)
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="bookcase_updated",
            details={
                "bookcase_id": str(item.id),
                "name": item.name,
                "previous_name": previous_name,
            },
        )
        self._commit(
            "A bookcase with this name already exists in the library."
        )
        return item

    def delete_bookcase(
        self, *, library_id: UUID, bookcase_id: UUID, actor_user_id: UUID
    ) -> None:
        item = self._repository.find_bookcase(library_id, bookcase_id)
        if item is None:
            raise PhysicalLibraryNotFoundError("Bookcase not found.")
        shelf_count = self._repository.shelf_count(library_id, bookcase_id)
        if shelf_count:
            raise PhysicalLibraryConflictError(
                f"Move or delete its {shelf_count} "
                f"{'shelf' if shelf_count == 1 else 'shelves'} before deleting this bookcase."
            )
        details = {"bookcase_id": str(item.id), "name": item.name}
        self._repository.delete(item)
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="bookcase_deleted",
            details=details,
        )
        self._commit("This bookcase cannot be deleted while records depend on it.")

    def create_shelf(
        self, *, library_id: UUID, actor_user_id: UUID, payload: ShelfWrite
    ) -> Shelf:
        if self._repository.find_bookcase(library_id, payload.bookcase_id) is None:
            raise PhysicalLibraryNotFoundError("Bookcase not found.")
        item = Shelf(library_id=library_id, **payload.model_dump())
        return self._save_created(
            item,
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="shelf_created",
            details=lambda: {
                "shelf_id": str(item.id),
                "bookcase_id": str(item.bookcase_id),
                "shelf_number": item.shelf_number,
            },
            conflict="This shelf number already exists in the selected bookcase.",
        )

    def update_shelf(
        self,
        *,
        library_id: UUID,
        shelf_id: UUID,
        actor_user_id: UUID,
        payload: ShelfUpdate,
    ) -> Shelf:
        item = self._repository.find_shelf(library_id, shelf_id)
        if item is None:
            raise PhysicalLibraryNotFoundError("Shelf not found.")
        previous_number = item.shelf_number
        collision = self._repository.shelf_with_number(
            bookcase_id=item.bookcase_id, shelf_number=payload.shelf_number
        )
        if collision is not None and collision.id != item.id:
            temporary = self._repository.next_shelf_number(item.bookcase_id)
            item.shelf_number = temporary
            self._repository.flush()
            collision.shelf_number = previous_number
            collision.updated_at = datetime.now(UTC)
            self._repository.flush()
        item.shelf_number = payload.shelf_number
        item.usable_height_mm = payload.usable_height_mm
        item.usable_width_mm = payload.usable_width_mm
        item.usable_depth_mm = payload.usable_depth_mm
        item.updated_at = datetime.now(UTC)
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="shelf_updated",
            details={
                "shelf_id": str(item.id),
                "bookcase_id": str(item.bookcase_id),
                "shelf_number": item.shelf_number,
                "previous_number": previous_number,
                "swapped_shelf_id": str(collision.id)
                if collision is not None and collision.id != item.id
                else None,
            },
        )
        self._commit("This shelf could not be updated because its number conflicts.")
        return item

    def delete_shelf(
        self, *, library_id: UUID, shelf_id: UUID, actor_user_id: UUID
    ) -> None:
        item = self._repository.find_shelf(library_id, shelf_id)
        if item is None:
            raise PhysicalLibraryNotFoundError("Shelf not found.")
        container_count = self._repository.container_count(library_id, shelf_id)
        if container_count:
            raise PhysicalLibraryConflictError(
                f"Move or delete its {container_count} container"
                f"{'s' if container_count != 1 else ''} before deleting this shelf."
            )
        details = {
            "shelf_id": str(item.id),
            "bookcase_id": str(item.bookcase_id),
            "shelf_number": item.shelf_number,
        }
        self._repository.delete(item)
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="shelf_deleted",
            details=details,
        )
        self._commit("This shelf cannot be deleted while records depend on it.")

    def create_container(
        self, *, library_id: UUID, actor_user_id: UUID, payload: ContainerWrite
    ) -> Container:
        if self._repository.find_shelf(library_id, payload.shelf_id) is None:
            raise PhysicalLibraryNotFoundError("Shelf not found.")
        item = Container(library_id=library_id, **payload.model_dump())
        return self._save_created(
            item,
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="container_created",
            details=lambda: {
                "container_id": str(item.id),
                "shelf_id": str(item.shelf_id),
                "container_type": item.container_type,
                "layer": item.layer,
                "container_number": item.container_number,
            },
            conflict=(
                "This row or pile number already exists in the selected shelf and layer."
            ),
        )

    def update_container(
        self,
        *,
        library_id: UUID,
        container_id: UUID,
        actor_user_id: UUID,
        payload: ContainerUpdate,
    ) -> Container:
        item = self._repository.find_container(library_id, container_id)
        if item is None:
            raise PhysicalLibraryNotFoundError("Container not found.")
        previous_number = item.container_number
        collision = self._repository.container_with_number(
            shelf_id=item.shelf_id,
            container_type=item.container_type,
            layer=item.layer,
            container_number=payload.container_number,
        )
        if collision is not None and collision.id != item.id:
            temporary = self._repository.next_container_number(
                shelf_id=item.shelf_id,
                container_type=item.container_type,
                layer=item.layer,
            )
            item.container_number = temporary
            self._repository.flush()
            collision.container_number = previous_number
            collision.updated_at = datetime.now(UTC)
            self._repository.flush()
        item.container_number = payload.container_number
        item.updated_at = datetime.now(UTC)
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="container_updated",
            details={
                "container_id": str(item.id),
                "shelf_id": str(item.shelf_id),
                "container_number": item.container_number,
                "previous_number": previous_number,
                "swapped_container_id": str(collision.id)
                if collision is not None and collision.id != item.id
                else None,
            },
        )
        self._commit(
            "This container could not be updated because its number conflicts."
        )
        return item

    def delete_container(
        self, *, library_id: UUID, container_id: UUID, actor_user_id: UUID
    ) -> None:
        item = self._repository.find_container(library_id, container_id)
        if item is None:
            raise PhysicalLibraryNotFoundError("Container not found.")
        book_count = self._repository.books_in_container(library_id, container_id)
        if book_count:
            raise PhysicalLibraryConflictError(
                f"Move its {book_count} book{'s' if book_count != 1 else ''} "
                "before deleting this container."
            )
        supported_piles = self._repository.supported_piles(library_id, container_id)
        if supported_piles:
            raise PhysicalLibraryConflictError(
                f"Reassign the {supported_piles} supported pile"
                f"{'s' if supported_piles != 1 else ''} before deleting this container."
            )
        details = {
            "container_id": str(item.id),
            "shelf_id": str(item.shelf_id),
            "container_type": item.container_type,
            "layer": item.layer,
            "container_number": item.container_number,
        }
        self._repository.delete(item)
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="container_deleted",
            details=details,
        )
        self._commit("This container cannot be deleted while records depend on it.")

    def _save_created(
        self,
        item: Bookcase | Shelf | Container,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        event_type: str,
        details: Callable[[], dict[str, object]],
        conflict: str,
    ) -> Bookcase | Shelf | Container:
        self._repository.add_all([item])
        try:
            self._repository.flush()
            self._repository.audit(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type=event_type,
                details=details(),
            )
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise PhysicalLibraryConflictError(conflict) from exc
        return item

    def _commit(self, conflict: str) -> None:
        try:
            self._repository.commit()
        except IntegrityError as exc:
            self._repository.rollback()
            raise PhysicalLibraryConflictError(conflict) from exc
