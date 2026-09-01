from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import case, func, select, update
from sqlalchemy.orm import Session

from ..models import (
    Book,
    Bookcase,
    Container,
    LibraryAuditEvent,
    Shelf,
    VisualContainerLayout,
)


class PhysicalLibraryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_bookcases(self, library_id: UUID) -> list[Bookcase]:
        return list(
            self._session.scalars(
                select(Bookcase)
                .where(Bookcase.library_id == library_id)
                .order_by(func.lower(Bookcase.name), Bookcase.id)
            )
        )

    def list_shelves(self, library_id: UUID) -> list[Shelf]:
        return list(
            self._session.scalars(
                select(Shelf)
                .where(Shelf.library_id == library_id)
                .order_by(Shelf.bookcase_id, Shelf.shelf_number, Shelf.id)
            )
        )

    def list_containers(self, library_id: UUID) -> list[Container]:
        return list(
            self._session.scalars(
                select(Container)
                .where(Container.library_id == library_id)
                .order_by(
                    Container.shelf_id,
                    case((Container.layer == "BACKGROUND", 0), else_=1),
                    case((Container.container_type == "ROW", 0), else_=1),
                    Container.container_number,
                    Container.id,
                )
            )
        )

    def book_counts(self, library_id: UUID) -> dict[UUID, int]:
        rows = self._session.execute(
            select(Book.container_id, func.count(Book.id))
            .where(Book.library_id == library_id, Book.container_id.is_not(None))
            .group_by(Book.container_id)
        )
        return {container_id: count for container_id, count in rows if container_id}

    def list_books(self, library_id: UUID) -> list[Book]:
        return list(
            self._session.scalars(
                select(Book)
                .where(Book.library_id == library_id)
                .order_by(func.lower(Book.title), func.lower(Book.author), Book.id)
            )
        )

    def find_book(self, library_id: UUID, book_id: UUID) -> Book | None:
        return self._session.scalar(
            select(Book).where(Book.library_id == library_id, Book.id == book_id)
        )

    def positioned_books(
        self, library_id: UUID, container_ids: set[UUID]
    ) -> dict[UUID, list[Book]]:
        result = {container_id: [] for container_id in container_ids}
        if not container_ids:
            return result
        books = self._session.scalars(
            select(Book)
            .where(
                Book.library_id == library_id,
                Book.container_id.in_(container_ids),
            )
            .order_by(Book.container_id, Book.position, Book.id)
            .with_for_update()
        )
        for book in books:
            if book.container_id is not None:
                result[book.container_id].append(book)
        return result

    def replace_placements(
        self,
        *,
        library_id: UUID,
        affected_containers: set[UUID],
        placements: dict[UUID, tuple[UUID | None, int | None]],
    ) -> None:
        # Vacate all affected unique positions first so updates remain valid on
        # both PostgreSQL and SQLite regardless of statement ordering.
        if affected_containers:
            self._session.execute(
                update(Book)
                .where(
                    Book.library_id == library_id,
                    Book.container_id.in_(affected_containers),
                )
                .values(position=Book.position + 1_000_000)
                .execution_options(synchronize_session=False)
            )
        for book_id, (container_id, position) in placements.items():
            self._session.execute(
                update(Book)
                .where(Book.library_id == library_id, Book.id == book_id)
                .values(
                    container_id=container_id,
                    position=position,
                    updated_at=func.now(),
                )
                .execution_options(synchronize_session=False)
            )

    def find_bookcase(self, library_id: UUID, item_id: UUID) -> Bookcase | None:
        return self._session.scalar(
            select(Bookcase).where(
                Bookcase.library_id == library_id, Bookcase.id == item_id
            )
        )

    def find_shelf(self, library_id: UUID, item_id: UUID) -> Shelf | None:
        return self._session.scalar(
            select(Shelf).where(Shelf.library_id == library_id, Shelf.id == item_id)
        )

    def find_container(self, library_id: UUID, item_id: UUID) -> Container | None:
        return self._session.scalar(
            select(Container).where(
                Container.library_id == library_id, Container.id == item_id
            )
        )

    def shelf_with_number(
        self, *, bookcase_id: UUID, shelf_number: int
    ) -> Shelf | None:
        return self._session.scalar(
            select(Shelf).where(
                Shelf.bookcase_id == bookcase_id,
                Shelf.shelf_number == shelf_number,
            )
        )

    def container_with_number(
        self,
        *,
        shelf_id: UUID,
        container_type: str,
        layer: str,
        container_number: int,
    ) -> Container | None:
        return self._session.scalar(
            select(Container).where(
                Container.shelf_id == shelf_id,
                Container.container_type == container_type,
                Container.layer == layer,
                Container.container_number == container_number,
            )
        )

    def next_shelf_number(self, bookcase_id: UUID) -> int:
        return (
            self._session.scalar(
                select(func.coalesce(func.max(Shelf.shelf_number), 0)).where(
                    Shelf.bookcase_id == bookcase_id
                )
            )
            or 0
        ) + 1

    def next_container_number(
        self, *, shelf_id: UUID, container_type: str, layer: str
    ) -> int:
        return (
            self._session.scalar(
                select(func.coalesce(func.max(Container.container_number), 0)).where(
                    Container.shelf_id == shelf_id,
                    Container.container_type == container_type,
                    Container.layer == layer,
                )
            )
            or 0
        ) + 1

    def shelf_count(self, library_id: UUID, bookcase_id: UUID) -> int:
        return self._session.scalar(
            select(func.count(Shelf.id)).where(
                Shelf.library_id == library_id, Shelf.bookcase_id == bookcase_id
            )
        ) or 0

    def container_count(self, library_id: UUID, shelf_id: UUID) -> int:
        return self._session.scalar(
            select(func.count(Container.id)).where(
                Container.library_id == library_id, Container.shelf_id == shelf_id
            )
        ) or 0

    def books_in_container(self, library_id: UUID, container_id: UUID) -> int:
        return self._session.scalar(
            select(func.count(Book.id)).where(
                Book.library_id == library_id, Book.container_id == container_id
            )
        ) or 0

    def supported_piles(self, library_id: UUID, container_id: UUID) -> int:
        return self._session.scalar(
            select(func.count(VisualContainerLayout.container_id)).where(
                VisualContainerLayout.library_id == library_id,
                VisualContainerLayout.pile_support_container_id == container_id,
            )
        ) or 0

    def add_all(self, items: Sequence[object]) -> None:
        self._session.add_all(items)

    def delete(self, item: object) -> None:
        self._session.delete(item)

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

    def expire_all(self) -> None:
        self._session.expire_all()
