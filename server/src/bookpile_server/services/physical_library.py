from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
import json
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from ..models import Book, Bookcase, Container, Shelf
from ..repositories.physical_library import PhysicalLibraryRepository
from ..schemas import (
    BookcaseWrite,
    BookPlacementWrite,
    RearrangementApplyRequest,
    RearrangementRequest,
    RearrangementResultResponse,
    ContainerUpdate,
    ContainerWrite,
    ShelfUpdate,
    ShelfWrite,
    VisualBookcaseLayoutWrite,
    VisualContainerLayoutWrite,
    VisualLayoutResponse,
    VisualLayoutWrite,
    VisualOutsideAreaWrite,
    VisualShelfLayoutWrite,
)
from .rearrangement import (
    PlannedBook,
    PlannedContainer,
    PlannedDraft,
    RearrangementPlanError,
    plan as plan_rearrangement,
    revision as rearrangement_revision,
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
    layout: VisualLayoutResponse


class PhysicalLibraryService:
    def __init__(self, repository: PhysicalLibraryRepository) -> None:
        self._repository = repository

    def hierarchy(self, library_id: UUID) -> PhysicalHierarchy:
        bookcases = self._repository.list_bookcases(library_id)
        shelves = self._repository.list_shelves(library_id)
        containers = self._repository.list_containers(library_id)
        book_counts = self._repository.book_counts(library_id)
        return PhysicalHierarchy(
            bookcases=bookcases,
            shelves=shelves,
            containers=containers,
            book_counts=book_counts,
            books=self._repository.list_books(library_id),
            layout=self._project_layout(
                library_id=library_id,
                bookcases=bookcases,
                shelves=shelves,
                containers=containers,
            ),
        )

    def update_visual_layout(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        payload: VisualLayoutWrite,
    ) -> None:
        library = self._repository.lock_library(library_id)
        if library is None:
            raise PhysicalLibraryNotFoundError("Library not found.")
        current = self.hierarchy(library_id)
        if payload.revision != current.layout.revision:
            raise PhysicalLibraryConflictError(
                "The layout changed after you opened the editor. Reload it before saving."
            )
        self._validate_layout(current, payload)
        library.geometry_mode = payload.geometry_mode
        self._repository.upsert_visual_layout(
            library_id=library_id,
            bookcases=[item.model_dump() for item in payload.bookcases],
            shelves=[item.model_dump() for item in payload.shelves],
            containers=[item.model_dump() for item in payload.containers],
            outside_areas=[item.model_dump() for item in payload.outside_areas],
        )
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="visual_layout_updated",
            details={
                "previous_revision": current.layout.revision,
                "bookcase_count": len(payload.bookcases),
                "shelf_count": len(payload.shelves),
                "container_count": len(payload.containers),
            },
        )
        self._commit("The visual layout could not be saved.")
        self._repository.expire_all()

    def _project_layout(
        self,
        *,
        library_id: UUID,
        bookcases: list[Bookcase],
        shelves: list[Shelf],
        containers: list[Container],
    ) -> VisualLayoutResponse:
        stored_bookcases = {
            item.bookcase_id: item
            for item in self._repository.list_bookcase_layouts(library_id)
        }
        stored_shelves = {
            item.shelf_id: item
            for item in self._repository.list_shelf_layouts(library_id)
        }
        stored_containers = {
            item.container_id: item
            for item in self._repository.list_container_layouts(library_id)
        }
        stored_outside = {
            item.area_kind: item
            for item in self._repository.list_outside_areas(library_id)
        }
        library = self._repository.find_library(library_id)
        if library is None:
            raise PhysicalLibraryNotFoundError("Library not found.")

        bookcase_layouts = []
        for index, item in enumerate(bookcases):
            stored = stored_bookcases.get(item.id)
            bookcase_layouts.append(
                VisualBookcaseLayoutWrite(
                    bookcase_id=item.id,
                    x_mm=float(stored.x_mm) if stored else index * 600.0,
                    floor_y_mm=float(stored.floor_y_mm) if stored else 1800.0,
                    width_mm=float(stored.width_mm) if stored else 500.0,
                    height_mm=float(stored.height_mm) if stored else 1600.0,
                )
            )

        shelf_layouts = [
            VisualShelfLayoutWrite(
                shelf_id=item.id,
                height_weight=(float(stored_shelves[item.id].height_weight)
                               if item.id in stored_shelves else 1.0),
            )
            for item in shelves
        ]

        grouped: dict[tuple[UUID, str], list[Container]] = {}
        for item in containers:
            grouped.setdefault((item.shelf_id, item.layer), []).append(item)
        defaults: dict[UUID, tuple[float, float, float, float]] = {}
        for (_shelf_id, layer), items in grouped.items():
            gap = 2.0
            width = (100.0 - gap * (len(items) - 1)) / len(items)
            for index, item in enumerate(items):
                defaults[item.id] = (
                    (width + gap) * index,
                    0.0 if layer == "BACKGROUND" else 50.0,
                    width,
                    100.0 if layer == "BACKGROUND" else 50.0,
                )
        container_layouts = []
        for item in containers:
            stored = stored_containers.get(item.id)
            default = defaults[item.id]
            container_layouts.append(
                VisualContainerLayoutWrite(
                    container_id=item.id,
                    x=float(stored.x) if stored else default[0],
                    y=float(stored.y) if stored else default[1],
                    width=float(stored.width) if stored else default[2],
                    height=float(stored.height) if stored else default[3],
                    row_anchor=stored.row_anchor if stored else "LEFT",
                    support_kind=stored.support_kind if stored else "SHELF",
                    support_container_id=(stored.support_container_id if stored else None),
                    pile_alignment=stored.pile_alignment if stored else "RIGHT",
                )
            )

        outside_defaults = {
            "READING": (700.0, 1500.0, 400.0, 400.0),
            "LOANED": (1200.0, 1500.0, 400.0, 400.0),
        }
        outside_layouts = []
        for kind in ("READING", "LOANED"):
            stored = stored_outside.get(kind)
            default = outside_defaults[kind]
            outside_layouts.append(
                VisualOutsideAreaWrite(
                    area_kind=kind,
                    x_mm=float(stored.x_mm) if stored else default[0],
                    y_mm=float(stored.y_mm) if stored else default[1],
                    width_mm=float(stored.width_mm) if stored else default[2],
                    height_mm=float(stored.height_mm) if stored else default[3],
                )
            )
        revision = self._layout_revision(
            bookcase_layouts, shelf_layouts, container_layouts, outside_layouts
        )
        return VisualLayoutResponse(
            revision=revision,
            geometry_mode=library.geometry_mode,
            coordinate_system_version=library.coordinate_system_version,
            bookcases=bookcase_layouts,
            shelves=shelf_layouts,
            containers=container_layouts,
            outside_areas=outside_layouts,
        )

    @staticmethod
    def _layout_revision(
        bookcases: list[VisualBookcaseLayoutWrite],
        shelves: list[VisualShelfLayoutWrite],
        containers: list[VisualContainerLayoutWrite],
        outside_areas: list[VisualOutsideAreaWrite],
    ) -> str:
        canonical = {
            "bookcases": [item.model_dump(mode="json") for item in bookcases],
            "shelves": [item.model_dump(mode="json") for item in shelves],
            "containers": [item.model_dump(mode="json") for item in containers],
            "outside_areas": [item.model_dump(mode="json") for item in outside_areas],
        }
        return sha256(
            json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()

    def _validate_layout(
        self, hierarchy: PhysicalHierarchy, payload: VisualLayoutWrite
    ) -> None:
        def require_complete(label: str, supplied: list[UUID], expected: set[UUID]) -> None:
            if len(supplied) != len(set(supplied)) or set(supplied) != expected:
                raise PhysicalLibraryValidationError(
                    f"The {label} layout is incomplete or contains duplicates."
                )

        require_complete(
            "bookcase",
            [item.bookcase_id for item in payload.bookcases],
            {item.id for item in hierarchy.bookcases},
        )
        require_complete(
            "shelf",
            [item.shelf_id for item in payload.shelves],
            {item.id for item in hierarchy.shelves},
        )
        require_complete(
            "container",
            [item.container_id for item in payload.containers],
            {item.id for item in hierarchy.containers},
        )
        outside_kinds = [item.area_kind for item in payload.outside_areas]
        if len(outside_kinds) != 2 or set(outside_kinds) != {"READING", "LOANED"}:
            raise PhysicalLibraryValidationError(
                "The Reading and On-loan areas must both be present exactly once."
            )

        contexts = {item.id: item for item in hierarchy.containers}
        layouts = {item.container_id: item for item in payload.containers}
        tolerance = 0.1

        for item in payload.containers:
            container = contexts[item.container_id]
            if item.support_kind == "SHELF":
                if item.support_container_id is not None:
                    raise PhysicalLibraryValidationError(
                        "A shelf-supported container cannot reference another container."
                    )
                if (
                    container.layer != "BACKGROUND"
                    and abs(item.y + item.height - 100.0) > tolerance
                ):
                    raise PhysicalLibraryValidationError(
                        "A shelf-supported container must rest on the shelf bottom."
                    )
                continue
            if item.support_kind != "CONTAINER" or item.support_container_id is None:
                raise PhysicalLibraryValidationError(
                    "Every container must rest on the shelf or on another container."
                )
            support = contexts.get(item.support_container_id)
            support_layout = layouts.get(item.support_container_id)
            if (
                support is None
                or support_layout is None
                or support.container_type == container.container_type
                or support.shelf_id != container.shelf_id
                or support.layer != container.layer
                or hierarchy.book_counts.get(support.id, 0) < 1
            ):
                raise PhysicalLibraryValidationError(
                    "A container must use a non-empty opposite-type support in the same shelf and layer."
                )
            horizontal_overlap = min(
                item.x + item.width, support_layout.x + support_layout.width
            ) - max(item.x, support_layout.x)
            if (
                horizontal_overlap <= tolerance
                or abs(item.y + item.height - support_layout.y) > tolerance
            ):
                raise PhysicalLibraryValidationError(
                    "The container geometry must visibly rest on its selected support."
                )

        for item in payload.containers:
            seen: set[UUID] = set()
            current = item
            while current.support_container_id is not None:
                if current.container_id in seen:
                    raise PhysicalLibraryValidationError(
                        "Container supports cannot form a cycle."
                    )
                seen.add(current.container_id)
                current = layouts[current.support_container_id]

        values = list(payload.containers)
        for index, first in enumerate(values):
            for second in values[index + 1:]:
                first_context = contexts[first.container_id]
                second_context = contexts[second.container_id]
                if first_context.shelf_id != second_context.shelf_id:
                    continue
                overlap_width = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
                overlap_height = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
                if overlap_width <= tolerance or overlap_height <= tolerance:
                    continue
                if first_context.layer == second_context.layer:
                    raise PhysicalLibraryValidationError(
                        "Containers in the same shelf layer cannot overlap."
                    )
                background = first if first_context.layer == "BACKGROUND" else second
                if overlap_height / background.height > 0.8:
                    raise PhysicalLibraryValidationError(
                        "Foreground containers may cover at most 80% of a background container's height."
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

    @staticmethod
    def _rearrangement_state(
        hierarchy: PhysicalHierarchy,
    ) -> tuple[dict[UUID, PlannedBook], dict[UUID, PlannedContainer]]:
        shelves = {item.id: item for item in hierarchy.shelves}
        bookcases = {item.id: item for item in hierarchy.bookcases}
        layouts = {item.container_id: item for item in hierarchy.layout.containers}
        books = {
            item.id: PlannedBook(
                id=item.id,
                title=item.title,
                author=item.author,
                page_count=item.page_count,
                container_id=item.container_id,
                position=item.position,
            )
            for item in hierarchy.books
        }
        containers: dict[UUID, PlannedContainer] = {}
        for item in hierarchy.containers:
            shelf = shelves[item.shelf_id]
            bookcase = bookcases[shelf.bookcase_id]
            layout = layouts[item.id]
            containers[item.id] = PlannedContainer(
                id=item.id,
                shelf_id=item.shelf_id,
                label=(
                    f"{bookcase.name} · Shelf {shelf.shelf_number} · "
                    f"{item.layer.title()} "
                    f"{'Row' if item.container_type == 'ROW' else 'Pile'} "
                    f"{item.container_number}"
                ),
                kind=item.container_type,
                layer=item.layer,
                x=layout.x,
                y=layout.y,
                width=layout.width,
                height=layout.height,
                row_anchor=layout.row_anchor,
                support_kind=layout.support_kind,
                support_container_id=layout.support_container_id,
                pile_alignment=layout.pile_alignment,
            )
        return books, containers

    @staticmethod
    def _projected_layout(
        hierarchy: PhysicalHierarchy, draft: PlannedDraft
    ) -> VisualLayoutWrite:
        projected = draft.containers
        return VisualLayoutWrite(
            revision=hierarchy.layout.revision,
            geometry_mode=hierarchy.layout.geometry_mode,
            coordinate_system_version=hierarchy.layout.coordinate_system_version,
            bookcases=hierarchy.layout.bookcases,
            shelves=hierarchy.layout.shelves,
            containers=[
                VisualContainerLayoutWrite(
                    container_id=item.container_id,
                    x=projected[item.container_id].x,
                    y=projected[item.container_id].y,
                    width=projected[item.container_id].width,
                    height=projected[item.container_id].height,
                    row_anchor=projected[item.container_id].row_anchor,
                    support_kind=projected[item.container_id].support_kind,
                    support_container_id=projected[item.container_id].support_container_id,
                    pile_alignment=projected[item.container_id].pile_alignment,
                )
                for item in hierarchy.layout.containers
            ],
            outside_areas=hierarchy.layout.outside_areas,
        )

    def _plan_rearrangement(
        self, *, library_id: UUID, payload: RearrangementRequest
    ) -> tuple[PhysicalHierarchy, PlannedDraft]:
        hierarchy = self.hierarchy(library_id)
        books, containers = self._rearrangement_state(hierarchy)
        try:
            draft = plan_rearrangement(books, containers, payload)
        except RearrangementPlanError as exc:
            raise PhysicalLibraryValidationError(str(exc)) from exc
        try:
            self._validate_layout(hierarchy, self._projected_layout(hierarchy, draft))
        except PhysicalLibraryValidationError as exc:
            errors = list(draft.payload["geometry_errors"])
            errors.append(str(exc))
            draft.payload["geometry_errors"] = list(dict.fromkeys(errors))
            draft.payload["warnings"] = list(dict.fromkeys([
                *draft.payload["warnings"], str(exc)
            ]))
            draft.payload["valid_to_apply"] = False
        return hierarchy, draft

    def preview_rearrangement(
        self, *, library_id: UUID, payload: RearrangementRequest
    ) -> RearrangementResultResponse:
        _hierarchy, draft = self._plan_rearrangement(
            library_id=library_id, payload=payload
        )
        return RearrangementResultResponse.model_validate(draft.payload)

    def apply_rearrangement(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        payload: RearrangementApplyRequest,
    ) -> RearrangementResultResponse:
        if self._repository.lock_library(library_id) is None:
            raise PhysicalLibraryNotFoundError("Library not found.")
        hierarchy, draft = self._plan_rearrangement(
            library_id=library_id,
            payload=RearrangementRequest.model_validate(payload.model_dump(exclude={"revision"})),
        )
        original_books, original_containers = self._rearrangement_state(hierarchy)
        current_revision = rearrangement_revision(original_books, original_containers)
        if payload.revision != current_revision:
            raise PhysicalLibraryConflictError(
                "The books or layout changed after this draft was opened. Reload before applying it."
            )
        result = RearrangementResultResponse.model_validate(draft.payload)
        if not result.valid_to_apply:
            raise PhysicalLibraryValidationError(
                "Complete the chain and resolve every gap or geometry conflict before applying it."
            )
        affected = {
            container_id
            for book_id, book in draft.books.items()
            for container_id in (original_books[book_id].container_id, book.container_id)
            if container_id is not None
            and (original_books[book_id].container_id, original_books[book_id].position)
            != (book.container_id, book.position)
        }
        placements = {
            book_id: (book.container_id, book.position)
            for book_id, book in draft.books.items()
            if original_books[book_id].container_id in affected
            or book.container_id in affected
            or (book.container_id, book.position)
            != (original_books[book_id].container_id, original_books[book_id].position)
        }
        layout = self._projected_layout(hierarchy, draft)
        self._repository.replace_placements(
            library_id=library_id,
            affected_containers=affected,
            placements=placements,
        )
        self._repository.upsert_visual_layout(
            library_id=library_id,
            bookcases=[item.model_dump() for item in layout.bookcases],
            shelves=[item.model_dump() for item in layout.shelves],
            containers=[item.model_dump() for item in layout.containers],
            outside_areas=[item.model_dump() for item in layout.outside_areas],
        )
        self._repository.audit(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="books_rearranged",
            details={
                "revision": current_revision,
                "movement_groups": result.movement_groups,
                "changed_book_count": len(result.placements),
                "changed_container_count": len(result.container_layouts),
            },
        )
        self._commit("The rearrangement could not be applied.")
        self._repository.expire_all()
        return result

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
