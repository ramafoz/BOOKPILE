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
