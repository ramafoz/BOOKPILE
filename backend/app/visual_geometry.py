"""Pure geometry rules for the visual-library map.

This module deliberately has no database access.  It is shared groundwork for
the read-only v7 audit, proportional rendering, and the later atomic
rearrangement validator.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from math import isfinite
from statistics import fmean
from typing import Iterable, Sequence


GEOMETRY_TOLERANCE = 0.1
LEGACY_SUPPORT_TOLERANCE = 3.0
COMPRESSION_LIMIT = 0.05
DEFAULT_EFFECTIVE_PAGES = 200.0
EMPTY_CONTAINER_INITIAL_FRACTION = 0.10


class ContainerKind(str, Enum):
    ROW = "ROW"
    PILE = "PILE"


class RowAnchor(str, Enum):
    LEFT = "LEFT"
    RIGHT = "RIGHT"


class SupportKind(str, Enum):
    SHELF = "SHELF"
    ROW = "ROW"
    AMBIGUOUS = "AMBIGUOUS"
    INVALID = "INVALID"


class CapacityState(str, Enum):
    FITS = "FITS"
    COMPRESSED = "COMPRESSED"
    INVALID = "INVALID"


@dataclass(frozen=True)
class Rect:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def bottom(self) -> float:
        return self.y + self.height


@dataclass(frozen=True)
class AuditContainer:
    id: int
    shelf_id: int
    layer: str
    kind: ContainerKind
    rect: Rect
    book_count: int


@dataclass(frozen=True)
class SupportInference:
    kind: SupportKind
    container_id: int | None = None
    candidates: tuple[int, ...] = ()
    detail: str = ""


@dataclass(frozen=True)
class Segment:
    offset: float
    thickness: float


@dataclass(frozen=True)
class SpanProjection:
    state: CapacityState
    span: float
    natural_span: float
    compression_ratio: float


def _valid_positive(value: int | float | None) -> bool:
    return value is not None and isfinite(value) and value > 0


def effective_page_mean(
    page_counts: Iterable[int | float | None],
    fallback: float = DEFAULT_EFFECTIVE_PAGES,
) -> float:
    """Return the arithmetic mean of valid positive page counts."""
    valid = [float(value) for value in page_counts if _valid_positive(value)]
    return fmean(valid) if valid else fallback


def effective_page_count(
    page_count: int | float | None,
    catalogue_mean: float,
) -> float:
    """Replace missing or invalid page counts with the catalogue mean."""
    if _valid_positive(page_count):
        return float(page_count)
    return catalogue_mean if _valid_positive(catalogue_mean) else DEFAULT_EFFECTIVE_PAGES


def proportional_segments(
    span: float,
    page_counts: Sequence[int | float | None],
    catalogue_mean: float,
) -> tuple[Segment, ...]:
    """Distribute an axis exactly by effective pages, without rounding."""
    if span < 0 or not isfinite(span):
        raise ValueError("Container span must be finite and non-negative")
    effective = [effective_page_count(value, catalogue_mean) for value in page_counts]
    total = sum(effective)
    if not effective or total <= 0:
        return ()
    offset = 0.0
    segments: list[Segment] = []
    for index, pages in enumerate(effective):
        thickness = span - offset if index == len(effective) - 1 else span * pages / total
        segments.append(Segment(offset=offset, thickness=thickness))
        offset += thickness
    return tuple(segments)


def intervals_overlap(
    first_start: float,
    first_end: float,
    second_start: float,
    second_end: float,
    tolerance: float = GEOMETRY_TOLERANCE,
) -> bool:
    """Return true only for a positive overlap, not merely touching edges."""
    return min(first_end, second_end) - max(first_start, second_start) > tolerance


def infer_pile_support(
    pile: AuditContainer,
    containers: Sequence[AuditContainer],
    tolerance: float = GEOMETRY_TOLERANCE,
) -> SupportInference:
    """Infer shelf/row support from a legacy v7 rectangle without writing it."""
    if pile.kind is not ContainerKind.PILE:
        raise ValueError("Support can only be inferred for piles")
    if abs(pile.rect.bottom - 100.0) <= tolerance:
        return SupportInference(SupportKind.SHELF, detail="Pile rests on shelf bottom")

    candidates = tuple(
        candidate.id
        for candidate in containers
        if candidate.kind is ContainerKind.ROW
        and candidate.shelf_id == pile.shelf_id
        and candidate.layer == pile.layer
        and candidate.book_count > 0
        and abs(candidate.rect.y - pile.rect.bottom) <= tolerance
        and intervals_overlap(
            pile.rect.x,
            pile.rect.right,
            candidate.rect.x,
            candidate.rect.right,
            tolerance,
        )
    )
    if len(candidates) == 1:
        return SupportInference(
            SupportKind.ROW,
            container_id=candidates[0],
            candidates=candidates,
            detail="Pile rests on one non-empty same-layer row",
        )
    if len(candidates) > 1:
        return SupportInference(
            SupportKind.AMBIGUOUS,
            candidates=candidates,
            detail="Pile touches multiple eligible supporting rows",
        )
    return SupportInference(
        SupportKind.INVALID,
        detail="Pile touches neither shelf bottom nor an eligible non-empty row",
    )


def is_full(span: float, capacity: float, tolerance: float = GEOMETRY_TOLERANCE) -> bool:
    return capacity > 0 and abs(capacity - span) <= tolerance


def project_occupied_span(
    *,
    current_span: float,
    current_pages: float,
    final_pages: float,
    capacity: float,
    release_space: bool = False,
    compression_limit: float = COMPRESSION_LIMIT,
) -> SpanProjection:
    """Project an occupied container's stacking span after page changes."""
    if not all(
        isfinite(value) and value >= 0
        for value in (current_span, current_pages, final_pages, capacity)
    ):
        raise ValueError("Geometry inputs must be finite and non-negative")
    if current_pages <= 0:
        raise ValueError("Use empty-container scale inference when current pages are zero")
    if final_pages == 0:
        return SpanProjection(CapacityState.FITS, 0.0, 0.0, 0.0)

    natural = current_span * final_pages / current_pages
    page_reduction = max(0.0, (current_pages - final_pages) / current_pages)
    if (
        final_pages <= current_pages
        and is_full(current_span, capacity)
        and page_reduction <= compression_limit
        and not release_space
    ):
        natural = capacity

    if natural <= capacity + GEOMETRY_TOLERANCE:
        return SpanProjection(CapacityState.FITS, min(natural, capacity), natural, 0.0)
    compression = (natural - capacity) / natural
    if compression <= compression_limit + 1e-12:
        return SpanProjection(CapacityState.COMPRESSED, capacity, natural, compression)
    return SpanProjection(CapacityState.INVALID, capacity, natural, compression)


def apply_axis_span(
    rect: Rect,
    kind: ContainerKind,
    span: float,
    row_anchor: RowAnchor = RowAnchor.LEFT,
) -> Rect:
    """Resize only the stacking axis while preserving its approved anchor."""
    if span < 0 or not isfinite(span):
        raise ValueError("Span must be finite and non-negative")
    if kind is ContainerKind.ROW:
        x = rect.right - span if row_anchor is RowAnchor.RIGHT else rect.x
        return Rect(x=x, y=rect.y, width=span, height=rect.height)
    return Rect(x=rect.x, y=rect.bottom - span, width=rect.width, height=span)


def page_count_warning(
    page_count: int | float | None,
    final_container_pages: float | None,
) -> bool:
    if not _valid_positive(page_count):
        return False
    pages = float(page_count)
    dominates_container = (
        final_container_pages is not None
        and final_container_pages > 0
        and pages / final_container_pages > 0.5
    )
    return pages > 2000 or dominates_container
