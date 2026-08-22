"""Container-geometry projection for atomic visual rearrangements."""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import fmean
from typing import Iterable, Mapping, Protocol

from .visual_geometry import (
    CapacityState,
    ContainerKind,
    EMPTY_CONTAINER_INITIAL_FRACTION,
    GEOMETRY_TOLERANCE,
    LEGACY_SUPPORT_TOLERANCE,
    Rect,
    RowAnchor,
    SupportKind,
    apply_axis_span,
    effective_page_count,
    effective_page_mean,
    intervals_overlap,
    page_count_warning,
    project_occupied_span,
)


class GeometryBook(Protocol):
    id: int
    container_id: int | None
    page_count: int | None


@dataclass(frozen=True)
class RearrangementContainer:
    id: int
    shelf_id: int
    bookcase_id: int
    label: str
    kind: ContainerKind
    layer: str
    rect: Rect
    row_anchor: RowAnchor
    support_kind: SupportKind | None
    support_container_id: int | None
    world_axis_factor: float


@dataclass(frozen=True)
class GeometryProjection:
    containers: dict[int, RearrangementContainer]
    warnings: tuple[str, ...]
    errors: tuple[str, ...]


def _books_in_container(
    books: Mapping[int, GeometryBook], container_id: int
) -> list[GeometryBook]:
    return [book for book in books.values() if book.container_id == container_id]


def _total_pages(books: Iterable[GeometryBook], catalogue_mean: float) -> float:
    return sum(effective_page_count(book.page_count, catalogue_mean) for book in books)


def stacking_capacity(
    container: RearrangementContainer,
    containers: Mapping[int, RearrangementContainer],
) -> float:
    """Return the maximum same-layer span available from the fixed anchor."""
    rect = container.rect
    peers = [
        peer
        for peer in containers.values()
        if peer.id != container.id
        and peer.shelf_id == container.shelf_id
        and peer.layer == container.layer
        and (
            intervals_overlap(rect.y, rect.bottom, peer.rect.y, peer.rect.bottom)
            if container.kind is ContainerKind.ROW
            else intervals_overlap(rect.x, rect.right, peer.rect.x, peer.rect.right)
        )
    ]
    if container.kind is ContainerKind.ROW:
        if container.row_anchor is RowAnchor.RIGHT:
            boundary = max(
                (peer.rect.right for peer in peers if peer.rect.right <= rect.right + GEOMETRY_TOLERANCE),
                default=0.0,
            )
            return max(0.0, rect.right - boundary)
        boundary = min(
            (peer.rect.x for peer in peers if peer.rect.x >= rect.x - GEOMETRY_TOLERANCE),
            default=100.0,
        )
        return max(0.0, boundary - rect.x)

    boundary = max(
        (peer.rect.bottom for peer in peers if peer.rect.bottom <= rect.bottom + GEOMETRY_TOLERANCE),
        default=0.0,
    )
    return max(0.0, rect.bottom - boundary)


def _scale_candidates(
    target: RearrangementContainer,
    containers: Mapping[int, RearrangementContainer],
    books: Mapping[int, GeometryBook],
    catalogue_mean: float,
    *,
    shelf_only: bool,
    bookcase_only: bool,
) -> list[float]:
    candidates: list[float] = []
    for candidate in containers.values():
        if candidate.id == target.id or candidate.kind is not target.kind:
            continue
        if shelf_only and candidate.shelf_id != target.shelf_id:
            continue
        if bookcase_only and candidate.bookcase_id != target.bookcase_id:
            continue
        candidate_books = _books_in_container(books, candidate.id)
        pages = _total_pages(candidate_books, catalogue_mean)
        if not candidate_books or pages <= 0 or candidate.world_axis_factor <= 0:
            continue
        world_span = (
            candidate.rect.width if candidate.kind is ContainerKind.ROW else candidate.rect.height
        ) * candidate.world_axis_factor
        candidates.append(world_span / pages / max(target.world_axis_factor, 1e-9))
    return candidates


def infer_empty_span(
    target: RearrangementContainer,
    containers: Mapping[int, RearrangementContainer],
    before_books: Mapping[int, GeometryBook],
    after_books: Mapping[int, GeometryBook],
    catalogue_mean: float,
    capacity: float,
) -> tuple[float, bool]:
    final_pages = _total_pages(_books_in_container(after_books, target.id), catalogue_mean)
    for shelf_only, bookcase_only in ((True, False), (False, True), (False, False)):
        scales = _scale_candidates(
            target,
            containers,
            before_books,
            catalogue_mean,
            shelf_only=shelf_only,
            bookcase_only=bookcase_only,
        )
        if scales:
            return min(capacity, final_pages * fmean(scales)), False
    return min(capacity, capacity * EMPTY_CONTAINER_INITIAL_FRACTION), True


def project_operation_geometry(
    containers: Mapping[int, RearrangementContainer],
    before_books: Mapping[int, GeometryBook],
    after_books: Mapping[int, GeometryBook],
    *,
    release_container_ids: set[int] | None = None,
) -> GeometryProjection:
    """Project one completed operation, preserving its sequential semantics."""
    projected = dict(containers)
    warnings: list[str] = []
    errors: list[str] = []
    catalogue_mean = effective_page_mean(book.page_count for book in before_books.values())
    affected = {
        container_id
        for book_id, book in after_books.items()
        for container_id in (before_books[book_id].container_id, book.container_id)
        if container_id is not None
        and before_books[book_id].container_id != book.container_id
    }

    # Shrink sources first. Destinations can then use the newly released capacity.
    affected_order = sorted(
        affected,
        key=lambda container_id: (
            _total_pages(_books_in_container(after_books, container_id), catalogue_mean)
            >= _total_pages(_books_in_container(before_books, container_id), catalogue_mean),
            container_id,
        ),
    )
    for container_id in affected_order:
        container = projected[container_id]
        before_items = _books_in_container(before_books, container_id)
        after_items = _books_in_container(after_books, container_id)
        before_pages = _total_pages(before_items, catalogue_mean)
        after_pages = _total_pages(after_items, catalogue_mean)
        if abs(before_pages - after_pages) <= 1e-9:
            continue
        capacity = stacking_capacity(container, projected)
        if capacity <= GEOMETRY_TOLERANCE:
            errors.append(f"{container.label} has no free stacking-axis capacity.")
            continue
        current_span = (
            container.rect.width if container.kind is ContainerKind.ROW else container.rect.height
        )
        if not after_items:
            # Empty containers remain as full-capacity destination shells.
            next_span = capacity
        elif before_items:
            span = project_occupied_span(
                current_span=current_span,
                current_pages=before_pages,
                final_pages=after_pages,
                capacity=capacity,
                release_space=(
                    container_id in (release_container_ids or set())
                ),
            )
            if span.state is CapacityState.INVALID:
                errors.append(
                    f"{container.label} would need {span.natural_span:.2f}% but only "
                    f"{capacity:.2f}% is available (maximum compression is 5%)."
                )
                continue
            if span.state is CapacityState.COMPRESSED:
                warnings.append(
                    f"{container.label} will compress its books by "
                    f"{span.compression_ratio * 100:.1f}%."
                )
            next_span = span.span
        else:
            next_span, used_fallback = infer_empty_span(
                container,
                projected,
                before_books,
                after_books,
                catalogue_mean,
                capacity,
            )
            if used_fallback:
                warnings.append(
                    f"{container.label} had no usable scale; its first book uses 10% "
                    "of the available space. Adjust it later in Edit layout."
                )
        projected[container_id] = replace(
            container,
            rect=apply_axis_span(
                container.rect,
                container.kind,
                next_span,
                container.row_anchor,
            ),
        )

    for container in projected.values():
        if container.kind is not ContainerKind.PILE:
            continue
        if (
            container.id not in affected
            and container.support_container_id not in affected
        ):
            continue
        items = _books_in_container(after_books, container.id)
        if not items:
            continue
        if container.support_kind is SupportKind.SHELF:
            if abs(container.rect.bottom - 100.0) > LEGACY_SUPPORT_TOLERANCE:
                errors.append(f"{container.label} no longer rests on the shelf.")
            continue
        support = projected.get(container.support_container_id or -1)
        support_items = _books_in_container(after_books, support.id) if support else []
        if (
            container.support_kind is not SupportKind.ROW
            or support is None
            or support.kind is not ContainerKind.ROW
            or support.shelf_id != container.shelf_id
            or support.layer != container.layer
            or not support_items
            or abs(container.rect.bottom - support.rect.y) > LEGACY_SUPPORT_TOLERANCE
            or not intervals_overlap(
                container.rect.x,
                container.rect.right,
                support.rect.x,
                support.rect.right,
            )
        ):
            errors.append(f"{container.label} has lost its valid row support.")

    projected_values = list(projected.values())
    for index, first in enumerate(projected_values):
        for second in projected_values[index + 1 :]:
            if first.shelf_id != second.shelf_id:
                continue
            if first.id not in affected and second.id not in affected:
                continue
            overlap_width = min(first.rect.right, second.rect.right) - max(
                first.rect.x, second.rect.x
            )
            overlap_height = min(first.rect.bottom, second.rect.bottom) - max(
                first.rect.y, second.rect.y
            )
            if overlap_width <= GEOMETRY_TOLERANCE or overlap_height <= GEOMETRY_TOLERANCE:
                continue
            if first.layer == second.layer:
                errors.append(
                    f"{first.label} would overlap {second.label} in the same shelf layer."
                )
                continue
            background = first if first.layer == "BACKGROUND" else second
            if overlap_height / background.rect.height > 0.8 + 1e-12:
                errors.append(
                    "Foreground containers may cover at most 80% of the "
                    f"background height in {background.label}."
                )

    moved_book_ids = {
        book_id
        for book_id, book in after_books.items()
        if before_books[book_id].container_id != book.container_id
    }
    for book_id in moved_book_ids:
        book = after_books[book_id]
        if book.container_id is None:
            continue
        final_pages = _total_pages(
            _books_in_container(after_books, book.container_id), catalogue_mean
        )
        if page_count_warning(book.page_count, final_pages):
            warnings.append(
                f'“{getattr(book, "title", "Book")}” is unusually large relative to its container.'
            )
    return GeometryProjection(projected, tuple(dict.fromkeys(warnings)), tuple(dict.fromkeys(errors)))


def container_layout_payload(
    original: Mapping[int, RearrangementContainer],
    planned: Mapping[int, RearrangementContainer],
) -> list[dict[str, float | int | str | None]]:
    result = []
    for container_id, container in planned.items():
        if container.rect == original[container_id].rect:
            continue
        result.append(
            {
                "id": container_id,
                "x": container.rect.x,
                "y": container.rect.y,
                "width": container.rect.width,
                "height": container.rect.height,
                "row_anchor": container.row_anchor.value,
                "pile_support_kind": (
                    container.support_kind.value if container.support_kind else None
                ),
                "pile_support_container_id": container.support_container_id,
            }
        )
    return result
