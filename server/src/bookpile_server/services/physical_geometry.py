"""Pure calculations for BOOKPILE's canonical physical geometry.

This module deliberately knows nothing about SQLAlchemy or HTTP.  The same
calculations can therefore be tested before any result is persisted and can
later be reused by Local without coupling the two editions' storage layers.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median
from typing import Iterable, Literal
from uuid import UUID


AxisSource = Literal["MEASURED", "PAGE_RATIO", "CATALOGUE_MEDIAN", "DEFAULT"]


@dataclass(frozen=True)
class BookMeasurement:
    id: UUID
    page_count: int | None = None
    height_mm: int | None = None
    width_mm: int | None = None
    thickness_mm: int | None = None


@dataclass(frozen=True)
class AxisValue:
    mm: float
    source: AxisSource


@dataclass(frozen=True)
class ResolvedBookMeasurement:
    id: UUID
    height: AxisValue
    width: AxisValue
    thickness: AxisValue


@dataclass(frozen=True)
class CatalogueDimensionDefaults:
    height_mm: float
    width_mm: float
    thickness_mm: float
    thickness_per_page: float | None


@dataclass(frozen=True)
class OccupiedSize:
    width_mm: float
    height_mm: float


@dataclass(frozen=True)
class GeometryDiagnostic:
    entity_kind: Literal["LIBRARY", "BOOKCASE", "SHELF", "CONTAINER", "BOOK"]
    entity_id: UUID | None
    severity: Literal["INFO", "WARNING", "ERROR"]
    code: str
    message: str


@dataclass(frozen=True)
class ContainerProjectionInput:
    id: UUID
    shelf_id: UUID
    kind: Literal["ROW", "PILE"]
    layer: Literal["BACKGROUND", "FOREGROUND"]
    x: float
    y: float
    width: float
    height: float
    row_anchor: Literal["LEFT", "RIGHT"]
    support_container_id: UUID | None
    pile_alignment: Literal["LEFT", "CENTER", "RIGHT"]
    shelf_width_mm: float
    shelf_height_mm: float
    books: tuple[ResolvedBookMeasurement, ...]


@dataclass
class ProjectedContainer:
    id: UUID
    x: float
    y: float
    width: float
    height: float


def _anchored_x(item: ContainerProjectionInput, width: float) -> float:
    if item.kind == "ROW":
        return item.x if item.row_anchor == "LEFT" else item.x + item.width - width
    if item.pile_alignment == "LEFT":
        return item.x
    if item.pile_alignment == "CENTER":
        return item.x + item.width / 2 - width / 2
    return item.x + item.width - width


def project_containers(
    inputs: Iterable[ContainerProjectionInput],
) -> tuple[dict[UUID, ProjectedContainer], list[GeometryDiagnostic]]:
    """Project truthful occupied sizes and make a best-effort accordion pass."""

    items = list(inputs)
    by_id = {item.id: item for item in items}
    projected: dict[UUID, ProjectedContainer] = {}
    diagnostics: list[GeometryDiagnostic] = []
    for item in items:
        size = occupied_size(item.kind, item.books)
        width = size.width_mm / item.shelf_width_mm * 100 if item.books else item.width
        height = size.height_mm / item.shelf_height_mm * 100 if item.books else item.height
        clearance = 100 - item.y - item.height
        projected[item.id] = ProjectedContainer(
            item.id,
            _anchored_x(item, width),
            100 - clearance - height if item.layer == "BACKGROUND" else 100 - height,
            width,
            height,
        )

    # Roots can accordion within their own shelf/layer. Dependants are placed
    # against their support afterwards and therefore travel with it.
    roots = [item for item in items if item.support_container_id is None]
    groups: dict[tuple[UUID, str], list[ContainerProjectionInput]] = {}
    for item in roots:
        groups.setdefault((item.shelf_id, item.layer), []).append(item)
    for group in groups.values():
        ordered = sorted(group, key=lambda item: (projected[item.id].x, str(item.id)))
        for _ in range(len(ordered) * 2):
            changed = False
            for left_item, right_item in zip(ordered, ordered[1:]):
                left = projected[left_item.id]
                right = projected[right_item.id]
                vertical = min(left.y + left.height, right.y + right.height) - max(left.y, right.y)
                overlap = left.x + left.width - right.x
                if vertical <= 0.1 or overlap <= 0.1:
                    continue
                if right.x + right.width + overlap <= 100.0:
                    right.x += overlap
                    changed = True
                elif left.x - overlap >= 0.0:
                    left.x -= overlap
                    changed = True
            if not changed:
                break

    unresolved = set(projected)
    while unresolved:
        progressed = False
        for container_id in list(unresolved):
            item = by_id[container_id]
            if item.support_container_id is None:
                unresolved.remove(container_id)
                progressed = True
                continue
            if item.support_container_id in unresolved:
                continue
            support = projected[item.support_container_id]
            current = projected[container_id]
            if item.kind == "ROW":
                current.x = support.x if item.row_anchor == "LEFT" else support.x + support.width - current.width
            elif item.pile_alignment == "LEFT":
                current.x = support.x
            elif item.pile_alignment == "CENTER":
                current.x = support.x + support.width / 2 - current.width / 2
            else:
                current.x = support.x + support.width - current.width
            current.y = support.y - current.height
            unresolved.remove(container_id)
            progressed = True
        if not progressed:
            break

    for item in items:
        rect = projected[item.id]
        if rect.x < -0.1 or rect.y < -0.1 or rect.x + rect.width > 100.1 or rect.y + rect.height > 100.1:
            diagnostics.append(GeometryDiagnostic(
                "CONTAINER", item.id, "WARNING", "OUTSIDE_SHELF",
                "The measured books extend beyond the usable shelf area.",
            ))
    for index, first_item in enumerate(items):
        first = projected[first_item.id]
        for second_item in items[index + 1:]:
            if first_item.shelf_id != second_item.shelf_id or first_item.layer != second_item.layer:
                continue
            second = projected[second_item.id]
            overlap_w = min(first.x + first.width, second.x + second.width) - max(first.x, second.x)
            overlap_h = min(first.y + first.height, second.y + second.height) - max(first.y, second.y)
            if overlap_w > 0.1 and overlap_h > 0.1:
                diagnostics.append(GeometryDiagnostic(
                    "CONTAINER", second_item.id, "WARNING", "SAME_LAYER_COLLISION",
                    "Measured container geometry collides with another container in this layer.",
                ))
    return projected, diagnostics


def _known(values: Iterable[int | None]) -> list[float]:
    return [float(value) for value in values if value is not None and value > 0]


def catalogue_dimension_defaults(
    books: Iterable[BookMeasurement],
) -> CatalogueDimensionDefaults:
    items = list(books)
    heights = _known(item.height_mm for item in items)
    widths = _known(item.width_mm for item in items)
    thicknesses = _known(item.thickness_mm for item in items)
    ratios = [
        float(item.thickness_mm) / item.page_count
        for item in items
        if item.thickness_mm is not None
        and item.thickness_mm > 0
        and item.page_count is not None
        and item.page_count > 0
    ]
    return CatalogueDimensionDefaults(
        height_mm=median(heights) if heights else 220.0,
        width_mm=median(widths) if widths else 150.0,
        thickness_mm=median(thicknesses) if thicknesses else 20.0,
        thickness_per_page=median(ratios) if ratios else None,
    )


def resolve_book_measurement(
    book: BookMeasurement, defaults: CatalogueDimensionDefaults
) -> ResolvedBookMeasurement:
    height = (
        AxisValue(float(book.height_mm), "MEASURED")
        if book.height_mm is not None and book.height_mm > 0
        else AxisValue(defaults.height_mm, "CATALOGUE_MEDIAN")
    )
    width = (
        AxisValue(float(book.width_mm), "MEASURED")
        if book.width_mm is not None and book.width_mm > 0
        else AxisValue(defaults.width_mm, "CATALOGUE_MEDIAN")
    )
    if book.thickness_mm is not None and book.thickness_mm > 0:
        thickness = AxisValue(float(book.thickness_mm), "MEASURED")
    elif (
        book.page_count is not None
        and book.page_count > 0
        and defaults.thickness_per_page is not None
    ):
        thickness = AxisValue(
            book.page_count * defaults.thickness_per_page, "PAGE_RATIO"
        )
    else:
        thickness = AxisValue(defaults.thickness_mm, "CATALOGUE_MEDIAN")
    return ResolvedBookMeasurement(
        id=book.id, height=height, width=width, thickness=thickness
    )


def occupied_size(
    container_type: Literal["ROW", "PILE"],
    books: Iterable[ResolvedBookMeasurement],
) -> OccupiedSize:
    items = list(books)
    if not items:
        return OccupiedSize(0.0, 0.0)
    total_thickness = sum(item.thickness.mm for item in items)
    longest_spine = max(item.height.mm for item in items)
    if container_type == "ROW":
        return OccupiedSize(total_thickness, longest_spine)
    return OccupiedSize(longest_spine, total_thickness)


def occupied_percentages(
    occupied: OccupiedSize,
    *,
    shelf_width_mm: int | None,
    shelf_height_mm: int | None,
) -> tuple[float | None, float | None]:
    """Return truthful shelf percentages where a physical scale is known."""

    width = (
        occupied.width_mm / shelf_width_mm * 100
        if shelf_width_mm is not None and shelf_width_mm > 0
        else None
    )
    height = (
        occupied.height_mm / shelf_height_mm * 100
        if shelf_height_mm is not None and shelf_height_mm > 0
        else None
    )
    return width, height


def measurement_diagnostics(
    book: BookMeasurement,
    resolved: ResolvedBookMeasurement,
    *,
    occupied_axis_mm: float | None = None,
) -> list[GeometryDiagnostic]:
    diagnostics: list[GeometryDiagnostic] = []
    measured = [book.height_mm, book.width_mm, book.thickness_mm]
    if any(value is not None and value > 2000 for value in measured):
        diagnostics.append(
            GeometryDiagnostic(
                "BOOK",
                book.id,
                "WARNING",
                "OVERSIZED_MEASUREMENT",
                "One or more recorded book dimensions exceed 2000 mm.",
            )
        )
    if occupied_axis_mm and resolved.thickness.mm > occupied_axis_mm * 0.5:
        diagnostics.append(
            GeometryDiagnostic(
                "BOOK",
                book.id,
                "WARNING",
                "LARGE_RELATIVE_THICKNESS",
                "This book occupies more than half of its container's stacking axis.",
            )
        )
    return diagnostics
