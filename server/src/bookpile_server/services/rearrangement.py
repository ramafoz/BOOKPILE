"""Pure, UUID-safe planning for Server visual book rearrangements."""

from __future__ import annotations

from dataclasses import dataclass, replace
from hashlib import sha256
import json
from statistics import fmean
from typing import Mapping
from uuid import UUID

from ..schemas import RearrangementOperationWrite, RearrangementRequest

Message = dict[str, object]


class RearrangementPlanError(Exception):
    pass


@dataclass(frozen=True)
class PlannedBook:
    id: UUID
    title: str
    author: str
    page_count: int | None
    container_id: UUID | None
    position: int | None


@dataclass(frozen=True)
class PlannedContainer:
    id: UUID
    shelf_id: UUID
    label: str
    kind: str
    layer: str
    x: float
    y: float
    width: float
    height: float
    row_anchor: str
    support_kind: str
    support_container_id: UUID | None
    pile_alignment: str


@dataclass(frozen=True)
class PlannedDraft:
    books: dict[UUID, PlannedBook]
    containers: dict[UUID, PlannedContainer]
    payload: dict[str, object]


def revision(
    books: Mapping[UUID, PlannedBook],
    containers: Mapping[UUID, PlannedContainer],
) -> str:
    canonical = {
        "books": [
            [str(book.id), str(book.container_id) if book.container_id else None, book.position]
            for book in sorted(books.values(), key=lambda item: str(item.id))
        ],
        "containers": [
            [
                str(item.id), item.x, item.y, item.width, item.height,
                item.row_anchor, item.support_kind,
                str(item.support_container_id) if item.support_container_id else None,
                item.pile_alignment,
            ]
            for item in sorted(containers.values(), key=lambda value: str(value.id))
        ],
    }
    return sha256(json.dumps(canonical, separators=(",", ":")).encode()).hexdigest()


def _occupancy(books: Mapping[UUID, PlannedBook]) -> dict[UUID, dict[int, UUID]]:
    result: dict[UUID, dict[int, UUID]] = {}
    for book in books.values():
        if book.container_id is not None and book.position is not None:
            result.setdefault(book.container_id, {})[book.position] = book.id
    return result


def _remove_occupant(occupancy: dict[UUID, dict[int, UUID]], book_id: UUID) -> None:
    for positions in occupancy.values():
        for position, occupant in list(positions.items()):
            if occupant == book_id:
                del positions[position]
                return


def _place(
    books: dict[UUID, PlannedBook], occupancy: dict[UUID, dict[int, UUID]],
    book_id: UUID, container_id: UUID, position: int,
) -> None:
    if position in occupancy.setdefault(container_id, {}):
        raise RearrangementPlanError("The destination remains occupied.")
    _remove_occupant(occupancy, book_id)
    occupancy[container_id][position] = book_id
    books[book_id] = replace(books[book_id], container_id=container_id, position=position)


def _remove_active(
    books: dict[UUID, PlannedBook], occupancy: dict[UUID, dict[int, UUID]],
    book_id: UUID, mode: str, affected: set[UUID],
) -> int:
    book = books[book_id]
    if book.container_id is None or book.position is None:
        return 0
    container_id, old_position = book.container_id, book.position
    _remove_occupant(occupancy, book_id)
    books[book_id] = replace(book, container_id=None, position=None)
    affected.add(container_id)
    if mode != "COLLAPSE":
        return 0
    shifted = 0
    positions = occupancy.setdefault(container_id, {})
    for position in sorted(value for value in positions if value > old_position):
        shifted_id = positions.pop(position)
        positions[position - 1] = shifted_id
        books[shifted_id] = replace(books[shifted_id], position=position - 1)
        shifted += 1
    return shifted


def _squeeze(
    books: dict[UUID, PlannedBook], occupancy: dict[UUID, dict[int, UUID]],
    container_id: UUID, position: int,
) -> int:
    positions = occupancy.setdefault(container_id, {})
    empty = position
    while empty in positions:
        empty += 1
    for current in range(empty - 1, position - 1, -1):
        shifted_id = positions.pop(current)
        positions[current + 1] = shifted_id
        books[shifted_id] = replace(books[shifted_id], position=current + 1)
    return empty - position


def _label(containers: Mapping[UUID, PlannedContainer], container_id: UUID, position: int) -> str:
    return f"{containers[container_id].label} · Position {position}"


def _shifted(count: int, reason: str) -> str:
    return f"{count} {'book' if count == 1 else 'books'} shifted {reason}."


def _message(code: str, **values: object) -> Message:
    return {"code": code, "values": values}


def _move_message(
    title: str, source: tuple[UUID, int], destination: tuple[UUID, int],
) -> Message:
    return _message(
        "BOOK_MOVED", title=title,
        source_container_id=str(source[0]), source_position=source[1],
        destination_container_id=str(destination[0]), destination_position=destination[1],
    )


def _shifted_message(count: int, reason: str) -> Message:
    return _message("BOOKS_SHIFTED", count=count, reason=reason)


def _plan_operation(
    original: Mapping[UUID, PlannedBook],
    containers: Mapping[UUID, PlannedContainer],
    operation: RearrangementOperationWrite,
) -> tuple[
    dict[UUID, PlannedBook], list[str], list[Message], list[str], list[Message],
    str, UUID | None, bool, set[UUID],
]:
    if operation.book_id not in original:
        raise RearrangementPlanError("Book not found.")
    books = dict(original)
    initial = books[operation.book_id]
    if initial.container_id is None or initial.position is None:
        raise RearrangementPlanError("The selected book has no physical position.")
    if not operation.steps:
        return books, [], [], [], [], operation.old_position_mode, initial.id, False, set()

    occupancy = _occupancy(books)
    affected: set[UUID] = set()
    log: list[str] = []
    log_messages: list[Message] = []
    warnings: list[str] = []
    warning_messages: list[Message] = []
    source = (initial.container_id, initial.position)
    first = operation.steps[0]
    target = occupancy.get(first.container_id, {}).get(first.position)
    effective_old = operation.old_position_mode
    if first.new_position_mode == "SWAP" and target not in (None, initial.id):
        effective_old = "LEAVE_GAP"
    collapsed = _remove_active(books, occupancy, initial.id, effective_old, affected)
    active_id: UUID | None = initial.id
    active_source_label = _label(containers, *source)
    active_source = source
    origin_gap_available = effective_old == "LEAVE_GAP"

    for index, step in enumerate(operation.steps):
        if active_id is None:
            raise RearrangementPlanError("This movement chain already has a destination.")
        if step.container_id not in containers:
            raise RearrangementPlanError("Destination container not found.")
        positions = occupancy.setdefault(step.container_id, {})
        if step.position > max(positions, default=0) + 1:
            raise RearrangementPlanError(
                "Destination must be an existing slot, a gap, or the next end position."
            )
        active = books[active_id]
        destination = _label(containers, step.container_id, step.position)
        target_id = positions.get(step.position)
        if target_id is None:
            _place(books, occupancy, active_id, step.container_id, step.position)
            affected.add(step.container_id)
            log.append(f'“{active.title}”: {active_source_label} → {destination}')
            log_messages.append(_move_message(active.title, active_source, (step.container_id, step.position)))
            if index == 0 and collapsed:
                log.append(_shifted(collapsed, "to occupy the gap"))
                log_messages.append(_shifted_message(collapsed, "OCCUPY_GAP"))
            active_id = None
            continue
        if step.new_position_mode == "SQUEEZE":
            squeezed = _squeeze(books, occupancy, step.container_id, step.position)
            _place(books, occupancy, active_id, step.container_id, step.position)
            affected.add(step.container_id)
            log.append(f'“{active.title}”: {active_source_label} → {destination}')
            log_messages.append(_move_message(active.title, active_source, (step.container_id, step.position)))
            if len(operation.steps) == 1 and source[0] == step.container_id:
                changed = sum(
                    1 for book_id, book in books.items() if book_id != initial.id
                    and (book.container_id, book.position)
                    != (original[book_id].container_id, original[book_id].position)
                )
                if changed:
                    log.append(_shifted(changed, "to fill the gap and make new room"))
                    log_messages.append(_shifted_message(changed, "FILL_GAP_AND_MAKE_ROOM"))
            else:
                if index == 0 and collapsed:
                    log.append(_shifted(collapsed, "to occupy the gap"))
                    log_messages.append(_shifted_message(collapsed, "OCCUPY_GAP"))
                if squeezed:
                    log.append(_shifted(squeezed, "to make room"))
                    log_messages.append(_shifted_message(squeezed, "MAKE_ROOM"))
            active_id = None
            continue
        if step.new_position_mode == "SWAP":
            if index and not origin_gap_available:
                raise RearrangementPlanError(
                    "Continue can finish with Swap only while its original gap remains available."
                )
            _remove_occupant(occupancy, target_id)
            _place(books, occupancy, active_id, step.container_id, step.position)
            _place(books, occupancy, target_id, *source)
            affected.update((step.container_id, source[0]))
            log.extend((
                f'“{active.title}”: {active_source_label} → {destination}',
                f'“{books[target_id].title}”: {destination} → {_label(containers, *source)}',
            ))
            log_messages.extend((
                _move_message(active.title, active_source, (step.container_id, step.position)),
                _move_message(books[target_id].title, (step.container_id, step.position), source),
            ))
            active_id = None
            origin_gap_available = False
            continue
        _remove_occupant(occupancy, target_id)
        _place(books, occupancy, active_id, step.container_id, step.position)
        affected.add(step.container_id)
        log.append(f'“{active.title}”: {active_source_label} → {destination}')
        log_messages.append(_move_message(active.title, active_source, (step.container_id, step.position)))
        active_id = target_id
        active_source_label = destination
        active_source = (step.container_id, step.position)
        books[target_id] = replace(books[target_id], container_id=None, position=None)
        warnings.append(f'Continue with “{books[target_id].title}”.')
        warning_messages.append(_message("CONTINUE_WITH_BOOK", title=books[target_id].title))

    return (
        books, log, log_messages, warnings, warning_messages, effective_old,
        active_id, active_id is None, affected,
    )


def _effective_pages(book: PlannedBook, mean: float) -> float:
    return float(book.page_count) if book.page_count and book.page_count > 0 else mean


def _container_pages(books: Mapping[UUID, PlannedBook], container_id: UUID, mean: float) -> float:
    return sum(_effective_pages(book, mean) for book in books.values() if book.container_id == container_id)


def _overlap(a1: float, a2: float, b1: float, b2: float) -> bool:
    return min(a2, b2) - max(a1, b1) > 0.1


def _capacity(item: PlannedContainer, containers: Mapping[UUID, PlannedContainer]) -> float:
    peers = [peer for peer in containers.values() if peer.id != item.id and peer.shelf_id == item.shelf_id and peer.layer == item.layer]
    if item.kind == "ROW":
        peers = [peer for peer in peers if _overlap(item.y, item.y + item.height, peer.y, peer.y + peer.height)]
        if item.row_anchor == "RIGHT":
            left = max((peer.x + peer.width for peer in peers if peer.x + peer.width <= item.x + item.width + 0.1), default=0.0)
            return max(0.0, item.x + item.width - left)
        right = min((peer.x for peer in peers if peer.x >= item.x - 0.1), default=100.0)
        return max(0.0, right - item.x)
    peers = [peer for peer in peers if _overlap(item.x, item.x + item.width, peer.x, peer.x + peer.width)]
    top = max((peer.y + peer.height for peer in peers if peer.y + peer.height <= item.y + item.height + 0.1), default=0.0)
    return max(0.0, item.y + item.height - top)


def _resize(item: PlannedContainer, span: float) -> PlannedContainer:
    if item.kind == "ROW":
        if item.row_anchor == "RIGHT":
            return replace(item, x=item.x + item.width - span, width=span)
        return replace(item, width=span)
    return replace(item, y=item.y + item.height - span, height=span)


def _project_geometry(
    containers: Mapping[UUID, PlannedContainer], original: Mapping[UUID, PlannedBook],
    planned: Mapping[UUID, PlannedBook], release: set[UUID],
) -> tuple[
    dict[UUID, PlannedContainer], list[str], list[str], list[Message], list[Message],
]:
    projected = dict(containers)
    known = [book.page_count for book in original.values() if book.page_count and book.page_count > 0]
    mean = fmean(known) if known else 200.0
    affected = {
        container_id for book_id, book in planned.items()
        for container_id in (original[book_id].container_id, book.container_id)
        if container_id is not None and original[book_id].container_id != book.container_id
    }
    warnings: list[str] = []
    errors: list[str] = []
    warning_messages: list[Message] = []
    error_messages: list[Message] = []
    for container_id in sorted(affected, key=str):
        item = projected[container_id]
        before = _container_pages(original, container_id, mean)
        after = _container_pages(planned, container_id, mean)
        if abs(before - after) < 1e-9:
            continue
        current = item.width if item.kind == "ROW" else item.height
        capacity = _capacity(item, projected)
        if capacity <= 0.1:
            errors.append(f"{item.label} has no free stacking-axis capacity.")
            error_messages.append(_message("NO_STACKING_CAPACITY", container_id=str(item.id)))
            continue
        if after == 0:
            target = capacity
        elif before > 0:
            natural = current * after / before
            if after < before and container_id not in release and after / before >= 0.95:
                target = current
            elif natural <= capacity:
                target = natural
            elif natural <= capacity * 1.05:
                target = capacity
                compression = round((1 - capacity / natural) * 100, 1)
                warnings.append(f"{item.label} will compress its books by {compression:.1f}%.")
                warning_messages.append(_message("BOOKS_COMPRESSED", container_id=str(item.id), percent=compression))
            else:
                errors.append(f"{item.label} needs {natural:.2f}% but only {capacity:.2f}% is available.")
                error_messages.append(_message(
                    "INSUFFICIENT_CAPACITY", container_id=str(item.id),
                    needed=round(natural, 2), available=round(capacity, 2),
                ))
                continue
        else:
            scales = []
            for peer in projected.values():
                pages = _container_pages(original, peer.id, mean)
                if peer.kind == item.kind and pages > 0:
                    scales.append((peer.width if peer.kind == "ROW" else peer.height) / pages)
            target = min(capacity, after * fmean(scales)) if scales else min(capacity, capacity * 0.1)
            if not scales:
                warnings.append(f"{item.label} had no known scale; its first book uses 10% of available space.")
                warning_messages.append(_message("UNKNOWN_SCALE", container_id=str(item.id)))
        projected[container_id] = _resize(item, max(0.1, target))
    return (
        projected, list(dict.fromkeys(warnings)), list(dict.fromkeys(errors)),
        warning_messages, error_messages,
    )


def _gaps(books: Mapping[UUID, PlannedBook], containers: set[UUID]) -> list[dict[str, object]]:
    occupancy = _occupancy(books)
    result = []
    for container_id in sorted(containers, key=str):
        positions = occupancy.get(container_id, {})
        missing = [value for value in range(1, max(positions, default=0) + 1) if value not in positions]
        if missing:
            result.append({"container_id": container_id, "positions": missing})
    return result


def plan(
    original: dict[UUID, PlannedBook], containers: dict[UUID, PlannedContainer],
    request: RearrangementRequest,
) -> PlannedDraft:
    operations = [*request.completed_operations, RearrangementOperationWrite(
        book_id=request.book_id,
        old_position_mode=request.old_position_mode,
        release_shelf_space=request.release_shelf_space,
        steps=request.steps,
    )]
    books = original
    groups: list[list[str]] = []
    message_groups: list[list[Message]] = []
    warnings: list[str] = []
    warning_messages: list[Message] = []
    affected: set[UUID] = set()
    release: set[UUID] = set()
    effective_old = request.old_position_mode
    next_active: UUID | None = request.book_id
    complete = False
    for index, operation in enumerate(operations):
        source = books.get(operation.book_id)
        (
            books, log, log_messages, operation_warnings, operation_warning_messages,
            effective_old, next_active, complete, operation_affected,
        ) = _plan_operation(books, containers, operation)
        if index < len(operations) - 1 and not complete:
            raise RearrangementPlanError("Every earlier movement chain must be complete.")
        if log:
            groups.append(log)
            message_groups.append(log_messages)
        warnings.extend(operation_warnings)
        warning_messages.extend(operation_warning_messages)
        affected.update(operation_affected)
        if operation.release_shelf_space and source and source.container_id:
            release.add(source.container_id)
    (
        projected, geometry_warnings, geometry_errors,
        geometry_warning_messages, geometry_error_messages,
    ) = _project_geometry(containers, original, books, release)
    warnings.extend(geometry_warnings)
    warning_messages.extend(geometry_warning_messages)
    placements = [
        {"book_id": book.id, "container_id": book.container_id, "position": book.position}
        for book in books.values()
        if (book.container_id, book.position) != (original[book.id].container_id, original[book.id].position)
    ]
    gaps = _gaps(books, affected)
    changed_layouts = [
        {
            "container_id": item.id, "x": item.x, "y": item.y,
            "width": item.width, "height": item.height,
            "row_anchor": item.row_anchor,
            "support_kind": item.support_kind,
            "support_container_id": item.support_container_id,
            "pile_alignment": item.pile_alignment,
        }
        for item in projected.values() if item != containers[item.id]
    ]
    payload: dict[str, object] = {
        "revision": revision(original, containers),
        "valid_to_apply": complete and not gaps and bool(placements) and not geometry_errors,
        "complete": complete,
        "effective_old_position_mode": effective_old,
        "next_active_book_id": next_active,
        "placements": placements,
        "gaps": gaps,
        "movement_log": [line for group in groups for line in group],
        "movement_groups": groups,
        "movement_message_groups": message_groups,
        "warnings": list(dict.fromkeys(warnings + geometry_errors)),
        "warning_messages": warning_messages + geometry_error_messages,
        "geometry_errors": geometry_errors,
        "geometry_error_messages": geometry_error_messages,
        "container_layouts": changed_layouts,
    }
    return PlannedDraft(books=books, containers=projected, payload=payload)
