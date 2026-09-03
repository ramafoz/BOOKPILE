"""Pure shelf/frame/separator projection for the shared visual map."""
from dataclasses import dataclass
from uuid import UUID


MIN_MM = 5.0
SHELF_SPAN_FALLBACK = 0.14


class ShelfGeometryError(ValueError):
    pass


@dataclass(frozen=True)
class ShelfSpec:
    shelf_id: UUID
    number: int
    measured_width_mm: float | None
    measured_height_mm: float | None
    alignment: str = "CENTER"
    offset_mm: float = 0.0
    open_top: bool = False
    left_frame_mm: float = 20.0
    right_frame_mm: float = 20.0
    top_closure_mm: float = 20.0
    bottom_board_mm: float = 20.0
    separator_after_mm: float | None = None
    separator_anchor: str = "BOTTOM"
    separator_height_mm: float | None = None


@dataclass(frozen=True)
class ShelfProjection:
    shelf_id: UUID
    x_mm: float
    floor_y_mm: float
    width_mm: float
    height_mm: float
    width_source: str
    height_source: str
    left_frame_mm: float
    right_frame_mm: float
    top_closure_mm: float
    bottom_board_mm: float
    separator_after_mm: float | None
    separator_anchor: str
    separator_height_mm: float | None
    separator_source: str | None


def _compress(values: list[float], fallback_indexes: list[int], available: float) -> list[float]:
    total = sum(values)
    if total <= available + 1e-6:
        return values
    fixed = total - sum(values[index] for index in fallback_indexes)
    fallback_available = available - fixed
    if not fallback_indexes or fallback_available < MIN_MM * len(fallback_indexes) - 1e-6:
        raise ShelfGeometryError("Entered shelf dimensions do not fit inside the furniture.")
    current = sum(values[index] for index in fallback_indexes)
    ratio = fallback_available / current
    result = list(values)
    for index in fallback_indexes:
        result[index] = max(MIN_MM, values[index] * ratio)
    if sum(result) > available + 1e-6:
        raise ShelfGeometryError("Shelf fallback dimensions cannot be compressed enough to fit.")
    return result


def _aligned_x(width: float, furniture_width: float, alignment: str, offset: float) -> float:
    if alignment == "LEFT":
        return offset
    if alignment == "RIGHT":
        return furniture_width - width + offset
    return (furniture_width - width) / 2 + offset


def project_shelves(
    *,
    furniture_width_mm: float,
    furniture_height_mm: float,
    direction: str,
    homogeneous: bool,
    frame_left_mm: float,
    frame_right_mm: float,
    top_closure_mm: float,
    bottom_closure_mm: float,
    separator_thickness_mm: float,
    shelves: list[ShelfSpec],
) -> list[ShelfProjection]:
    """Return fully contained, non-overlapping, furniture-local rectangles."""
    if furniture_width_mm <= 0 or furniture_height_mm <= 0:
        raise ShelfGeometryError("Furniture dimensions must be positive.")
    if any(value < 0 for value in (frame_left_mm, frame_right_mm, top_closure_mm, bottom_closure_mm)):
        raise ShelfGeometryError("Frame and closure dimensions cannot be negative.")
    if separator_thickness_mm < MIN_MM:
        raise ShelfGeometryError("Separators must be at least 5 mm thick.")
    if not shelves:
        return []

    ordered = sorted(shelves, key=lambda item: item.number)
    vertical = direction in {"TOP_TO_BOTTOM", "BOTTOM_TO_TOP"}
    separators = [
        (separator_thickness_mm if homogeneous else (item.separator_after_mm or separator_thickness_mm))
        for item in ordered[:-1]
    ]
    if any(value < MIN_MM for value in separators):
        raise ShelfGeometryError("Separators must be at least 5 mm thick.")

    projections: list[ShelfProjection] = []
    if vertical:
        heights = [item.measured_height_mm or furniture_height_mm * SHELF_SPAN_FALLBACK for item in ordered]
        fallback_indexes = [index for index, item in enumerate(ordered) if not item.measured_height_mm]
        available = furniture_height_mm - top_closure_mm - bottom_closure_mm - sum(separators)
        heights = _compress(heights, fallback_indexes, available)
        residual = max(0.0, available - sum(heights))
        effective_top = top_closure_mm + (residual if direction == "BOTTOM_TO_TOP" else 0)
        effective_bottom = bottom_closure_mm + (residual if direction == "TOP_TO_BOTTOM" else 0)
        cursor = furniture_height_mm - effective_top if direction == "TOP_TO_BOTTOM" else effective_bottom
        for index, (item, height) in enumerate(zip(ordered, heights, strict=True)):
            is_physical_top = index == 0 if direction == "TOP_TO_BOTTOM" else index == len(ordered) - 1
            if item.open_top and not is_physical_top:
                raise ShelfGeometryError("Only the physically uppermost shelf may be open.")
            left = 0.0 if item.open_top else (frame_left_mm if homogeneous else item.left_frame_mm)
            right = 0.0 if item.open_top else (frame_right_mm if homogeneous else item.right_frame_mm)
            measured_width = item.measured_width_mm
            width = measured_width or furniture_width_mm - left - right
            if item.open_top and measured_width is not None and abs(measured_width - furniture_width_mm) > 1e-6:
                raise ShelfGeometryError("An open top shelf with entered width must equal the furniture width.")
            if width < MIN_MM or width > furniture_width_mm + 1e-6:
                raise ShelfGeometryError("Shelf width does not fit inside the furniture.")
            x = _aligned_x(width, furniture_width_mm, item.alignment, item.offset_mm)
            if item.open_top:
                x = 0.0
            if x < -1e-6 or x + width > furniture_width_mm + 1e-6:
                raise ShelfGeometryError("Shelf alignment or offset places it outside the furniture.")
            floor = cursor - height if direction == "TOP_TO_BOTTOM" else cursor
            separator = separators[index] if index < len(separators) else None
            projections.append(ShelfProjection(
                item.shelf_id, x, floor, width, height,
                "ENTERED" if measured_width is not None else "FALLBACK",
                "ENTERED" if item.measured_height_mm is not None else "FALLBACK",
                left, right, 0.0 if item.open_top else item.top_closure_mm,
                item.bottom_board_mm, separator, item.separator_anchor,
                item.separator_height_mm, "FALLBACK" if separator is not None else None,
            ))
            cursor = floor - (separator or 0) if direction == "TOP_TO_BOTTOM" else floor + height + (separator or 0)
    else:
        widths = [item.measured_width_mm or furniture_width_mm * SHELF_SPAN_FALLBACK for item in ordered]
        fallback_indexes = [index for index, item in enumerate(ordered) if not item.measured_width_mm]
        base_available = furniture_width_mm - frame_left_mm - frame_right_mm - sum(separators)
        widths = _compress(widths, fallback_indexes, base_available)
        residual = max(0.0, base_available - sum(widths))
        effective_separators = list(separators)
        effective_left, effective_right = frame_left_mm, frame_right_mm
        if effective_separators:
            effective_separators = [value + residual / len(effective_separators) for value in effective_separators]
        elif effective_left > 0 and effective_right > 0:
            effective_left += residual / 2
            effective_right += residual / 2
        elif effective_left > 0:
            effective_left += residual
        elif effective_right > 0:
            effective_right += residual
        elif len(ordered) == 1 and ordered[0].measured_width_mm is None:
            widths[0] = furniture_width_mm
        cursor = effective_left if direction == "LEFT_TO_RIGHT" else furniture_width_mm - effective_right
        for index, (item, width) in enumerate(zip(ordered, widths, strict=True)):
            top = top_closure_mm if homogeneous else item.top_closure_mm
            bottom = bottom_closure_mm if homogeneous else item.bottom_board_mm
            measured_height = item.measured_height_mm
            height = measured_height or furniture_height_mm - top - bottom
            if height < MIN_MM or height > furniture_height_mm + 1e-6:
                raise ShelfGeometryError("Shelf height does not fit inside the furniture.")
            floor = bottom
            x = cursor if direction == "LEFT_TO_RIGHT" else cursor - width
            if x < -1e-6 or x + width > furniture_width_mm + 1e-6:
                raise ShelfGeometryError("Shelf widths do not fit inside the furniture.")
            separator = effective_separators[index] if index < len(effective_separators) else None
            separator_height = None
            if separator is not None:
                separator_height = furniture_height_mm if top > 0 else furniture_height_mm * .5
            projections.append(ShelfProjection(
                item.shelf_id, x, floor, width, height,
                "ENTERED" if item.measured_width_mm is not None else "FALLBACK",
                "ENTERED" if measured_height is not None else "FALLBACK",
                effective_left, effective_right, top, bottom, separator,
                "BOTTOM" if homogeneous else item.separator_anchor,
                separator_height if homogeneous else item.separator_height_mm,
                "DERIVED" if separator is not None else None,
            ))
            cursor = x + width + (separator or 0) if direction == "LEFT_TO_RIGHT" else x - (separator or 0)

    # Pairwise hard invariants, independent of direction or numbering.
    for index, first in enumerate(projections):
        if first.x_mm < -1e-6 or first.floor_y_mm < -1e-6 or first.x_mm + first.width_mm > furniture_width_mm + 1e-6 or first.floor_y_mm + first.height_mm > furniture_height_mm + 1e-6:
            raise ShelfGeometryError("A shelf would extend outside its furniture.")
        for second in projections[index + 1:]:
            overlap_x = min(first.x_mm + first.width_mm, second.x_mm + second.width_mm) - max(first.x_mm, second.x_mm)
            overlap_y = min(first.floor_y_mm + first.height_mm, second.floor_y_mm + second.height_mm) - max(first.floor_y_mm, second.floor_y_mm)
            if overlap_x > 1e-6 and overlap_y > 1e-6:
                raise ShelfGeometryError("Shelves cannot overlap.")
    return projections
