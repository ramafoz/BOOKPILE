import hashlib
import sqlite3
from dataclasses import dataclass, replace
from datetime import date
from typing import Any

from fastapi import HTTPException

from .schemas import (
    BookStatus,
    NewPositionMode,
    OldPositionMode,
    RearrangementDestinationKind,
    RearrangementOperation,
    RearrangementRequest,
    RearrangementStep,
)
from .reading_sessions import apply_projected_reading_values, sync_book_projection


REARRANGEMENT_BOOKS = """
SELECT
    b.id,
    b.title,
    b.author,
    b.status,
    b.container_id,
    b.position,
    b.acquisition_date,
    b.reading_started_date,
    b.read_date,
    b.is_read_date_unknown,
    EXISTS(
        SELECT 1 FROM reading_sessions rs
        WHERE rs.book_id = b.id AND rs.state = 'COMPLETED'
    ) AS has_completed_reading,
    EXISTS(
        SELECT 1 FROM loans loan
        WHERE loan.book_id = b.id AND loan.state = 'ACTIVE'
    ) AS is_on_loan,
    b.updated_at
FROM books b
ORDER BY b.id
"""

REARRANGEMENT_CONTAINERS = """
SELECT
    c.id,
    c.container_type,
    c.layer,
    c.container_number,
    s.shelf_number,
    bc.name AS bookcase_name
FROM containers c
JOIN shelves s ON s.id = c.shelf_id
JOIN bookcases bc ON bc.id = s.bookcase_id
ORDER BY c.id
"""


@dataclass(frozen=True)
class PlannedBook:
    id: int
    title: str
    author: str
    status: str
    container_id: int | None
    position: int | None
    acquisition_date: str | None
    reading_started_date: str | None
    read_date: str | None
    is_read_date_unknown: bool
    has_completed_reading: bool
    is_on_loan: bool
    updated_at: str


def load_rearrangement_state(
    connection: sqlite3.Connection,
) -> tuple[dict[int, PlannedBook], dict[int, str]]:
    books = {
        row["id"]: PlannedBook(
            id=row["id"],
            title=row["title"],
            author=row["author"],
            status=row["status"],
            container_id=row["container_id"],
            position=row["position"],
            acquisition_date=row["acquisition_date"],
            reading_started_date=row["reading_started_date"],
            read_date=row["read_date"],
            is_read_date_unknown=bool(row["is_read_date_unknown"]),
            has_completed_reading=bool(row["has_completed_reading"]),
            is_on_loan=bool(row["is_on_loan"]),
            updated_at=row["updated_at"],
        )
        for row in connection.execute(REARRANGEMENT_BOOKS)
    }
    containers = {
        row["id"]: (
            f'{row["bookcase_name"]} · Shelf {row["shelf_number"]} · '
            f'{str(row["layer"]).title()} '
            f'{str(row["container_type"]).title()} {row["container_number"]}'
        )
        for row in connection.execute(REARRANGEMENT_CONTAINERS)
    }
    return books, containers


def rearrangement_revision(books: dict[int, PlannedBook]) -> str:
    digest = hashlib.sha256()
    for book in books.values():
        digest.update(
            (
                f"{book.id}|{book.container_id}|{book.position}|"
                f"{book.status}|{int(book.is_on_loan)}|{book.updated_at}\n"
            ).encode("utf-8")
        )
    return digest.hexdigest()


def plan_rearrangement(
    original: dict[int, PlannedBook],
    containers: dict[int, str],
    request: RearrangementOperation,
) -> dict[str, Any]:
    if request.book_id not in original:
        raise HTTPException(status_code=404, detail="Book not found")

    books = dict(original)
    occupancy = build_occupancy(books)
    affected_containers: set[int] = set()
    movement_log: list[str] = []
    warnings: list[str] = []
    initial = books[request.book_id]
    # A loaned book is displayed in the loan area. Moving its reserved shelf
    # position must not finish or cancel a reading that remains active.
    was_reading = (
        initial.status == BookStatus.currently_reading.value
        and not initial.is_on_loan
    )
    active_id: int | None = initial.id
    initial_source = (initial.container_id, initial.position)
    effective_old_mode = request.old_position_mode

    if not request.steps:
        return result_payload(
            original,
            books,
            containers,
            affected_containers,
            movement_log,
            warnings,
            effective_old_mode,
            active_id,
            complete=False,
        )

    first_step = request.steps[0]
    if first_step.destination_kind == RearrangementDestinationKind.reading:
        if len(request.steps) != 1:
            raise HTTPException(
                status_code=422,
                detail="Moving to Reading must be the only rearrangement step",
            )
        if initial.status == BookStatus.currently_reading.value:
            raise HTTPException(status_code=422, detail="Book is already Reading")
        if initial.is_on_loan:
            raise HTTPException(
                status_code=422,
                detail="Return this book before starting a reading session",
            )
        books[initial.id] = transition_to_reading(initial)
        movement_log.append(
            f'“{initial.title}”: status '
            f'{"Read → Re-Reading" if initial.status == BookStatus.read.value else "Pending → Reading"}'
        )
        return result_payload(
            original,
            books,
            containers,
            affected_containers,
            movement_log,
            warnings,
            effective_old_mode,
            None,
            complete=True,
        )

    if initial.container_id is None or initial.position is None:
        raise HTTPException(
            status_code=422,
            detail="The active book has no retained physical position",
        )

    if was_reading:
        if first_step.reading_exit_status is None:
            raise HTTPException(
                status_code=422,
                detail="Choose the status to use when returning the Reading book",
            )
        if (
            initial.has_completed_reading
            and first_step.reading_exit_status == BookStatus.pending.value
        ):
            raise HTTPException(
                status_code=422,
                detail="A re-reading book can only return to the library as Read",
            )
        books[initial.id] = transition_from_reading(
            initial,
            first_step.reading_exit_status,
        )
        initial = books[initial.id]
        movement_log.append(
            f'“{initial.title}”: status Reading → '
            f'{"Read" if initial.status == BookStatus.read.value else "Pending"}'
        )
        if (
            first_step.container_id == initial_source[0]
            and first_step.position == initial_source[1]
        ):
            return result_payload(
                original,
                books,
                containers,
                affected_containers,
                movement_log,
                warnings,
                effective_old_mode,
                None,
                complete=True,
            )

    destination_occupant = occupant_at(
        occupancy,
        first_step.container_id,
        first_step.position,
    )
    if (
        first_step.new_position_mode == NewPositionMode.swap
        and destination_occupant not in (None, initial.id)
    ):
        effective_old_mode = OldPositionMode.leave_gap

    collapsed_count = remove_active(
        books,
        occupancy,
        initial.id,
        effective_old_mode,
        affected_containers,
    )

    origin_gap_available = effective_old_mode == OldPositionMode.leave_gap
    active_source_label = position_label(
        containers,
        initial_source[0],
        initial_source[1],
    )
    for step_index, step in enumerate(request.steps):
        if active_id is None:
            raise HTTPException(
                status_code=422,
                detail="The rearrangement chain already has a destination",
            )
        if step.destination_kind != RearrangementDestinationKind.physical:
            raise HTTPException(
                status_code=422,
                detail="Only the initial selected book can move to Reading",
            )
        if step.container_id is None or step.position is None:
            raise HTTPException(
                status_code=422,
                detail="Physical destinations require a container and position",
            )
        if step.container_id not in containers:
            raise HTTPException(status_code=404, detail="Container not found")

        validate_destination_position(occupancy, step.container_id, step.position)
        target_id = occupant_at(occupancy, step.container_id, step.position)
        if target_id is not None and books[target_id].status == BookStatus.currently_reading.value:
            raise HTTPException(
                status_code=422,
                detail="A Reading book's retained position is reserved",
            )

        active = books[active_id]
        destination_label = position_label(
            containers,
            step.container_id,
            step.position,
        )

        if target_id is None:
            place_book(books, occupancy, active_id, step.container_id, step.position)
            affected_containers.add(step.container_id)
            movement_log.append(
                f'“{active.title}”: {active_source_label} → {destination_label}'
            )
            if is_single_same_container_move(request, initial_source, step):
                append_net_shift_summary(movement_log, original, books, initial.id)
            elif step_index == 0 and collapsed_count:
                movement_log.append(
                    shifted_summary(collapsed_count, "to occupy the gap")
                )
            active_id = None
            continue

        if step.new_position_mode == NewPositionMode.squeeze:
            shifted = squeeze_destination(
                books,
                occupancy,
                step.container_id,
                step.position,
            )
            place_book(books, occupancy, active_id, step.container_id, step.position)
            affected_containers.add(step.container_id)
            movement_log.append(
                f'“{active.title}”: {active_source_label} → {destination_label}'
            )
            if is_single_same_container_move(request, initial_source, step):
                append_net_shift_summary(movement_log, original, books, initial.id)
            else:
                if step_index == 0 and collapsed_count:
                    movement_log.append(
                        shifted_summary(collapsed_count, "to occupy the gap")
                    )
                if shifted:
                    movement_log.append(
                        shifted_summary(len(shifted), "to make room")
                    )
            active_id = None
            continue

        if step.new_position_mode == NewPositionMode.swap:
            if step_index == 0:
                swap_container, swap_position = initial_source
            elif origin_gap_available:
                swap_container, swap_position = initial_source
            else:
                raise HTTPException(
                    status_code=422,
                    detail="A Continue chain can only finish with Swap when its original gap remains available",
                )
            if swap_container is None or swap_position is None:
                raise HTTPException(
                    status_code=422,
                    detail="Swap requires an original physical position",
                )
            remove_from_occupancy(occupancy, target_id)
            place_book(books, occupancy, active_id, step.container_id, step.position)
            place_book(books, occupancy, target_id, swap_container, swap_position)
            affected_containers.update((step.container_id, swap_container))
            movement_log.append(
                f'“{active.title}”: {active_source_label} → {destination_label}'
            )
            if step_index == 0 and collapsed_count:
                movement_log.append(
                    shifted_summary(collapsed_count, "to occupy the gap")
                )
            movement_log.append(
                f'“{books[target_id].title}”: {destination_label} → {position_label(containers, swap_container, swap_position)}'
            )
            active_id = None
            origin_gap_available = False
            continue

        remove_from_occupancy(occupancy, target_id)
        place_book(books, occupancy, active_id, step.container_id, step.position)
        affected_containers.add(step.container_id)
        movement_log.append(
            f'“{active.title}”: {active_source_label} → {destination_label}'
        )
        if step_index == 0 and collapsed_count:
            movement_log.append(
                shifted_summary(collapsed_count, "to occupy the gap")
            )
        active_id = target_id
        active_source_label = destination_label
        books[target_id] = replace(
            books[target_id],
            container_id=None,
            position=None,
        )
        warnings.append(f'Continue with “{books[target_id].title}”')

    complete = active_id is None
    return result_payload(
        original,
        books,
        containers,
        affected_containers,
        movement_log,
        warnings,
        effective_old_mode,
        active_id,
        complete=complete,
    )


def plan_rearrangement_draft(
    original: dict[int, PlannedBook],
    containers: dict[int, str],
    request: RearrangementRequest,
) -> dict[str, Any]:
    operations = [
        *request.completed_operations,
        RearrangementOperation(
            book_id=request.book_id,
            old_position_mode=request.old_position_mode,
            steps=request.steps,
        ),
    ]
    books = original
    movement_groups: list[list[str]] = []
    warnings: list[str] = []
    current_result: dict[str, Any] | None = None

    for index, operation in enumerate(operations):
        current_result = plan_rearrangement(books, containers, operation)
        if index < len(operations) - 1 and not current_result["complete"]:
            raise HTTPException(
                status_code=422,
                detail="Every earlier movement chain must be complete",
            )
        if current_result["movement_log"]:
            movement_groups.append(current_result["movement_log"])
        warnings.extend(current_result["warnings"])
        books = current_result["_planned_books"]

    assert current_result is not None
    affected = {
        container_id
        for book_id, book in books.items()
        for container_id in (
            original[book_id].container_id,
            book.container_id,
        )
        if container_id is not None
        and (
            original[book_id].container_id,
            original[book_id].position,
        ) != (book.container_id, book.position)
    }
    flattened_log = [line for group in movement_groups for line in group]
    result = result_payload(
        original,
        books,
        containers,
        affected,
        flattened_log,
        warnings,
        OldPositionMode(current_result["effective_old_position_mode"]),
        current_result["next_active_book_id"],
        complete=current_result["complete"],
    )
    result["movement_groups"] = movement_groups
    return result


def build_occupancy(books: dict[int, PlannedBook]) -> dict[int, dict[int, int]]:
    occupancy: dict[int, dict[int, int]] = {}
    for book in books.values():
        if book.container_id is not None and book.position is not None:
            occupancy.setdefault(book.container_id, {})[book.position] = book.id
    return occupancy


def occupant_at(
    occupancy: dict[int, dict[int, int]],
    container_id: int | None,
    position: int | None,
) -> int | None:
    if container_id is None or position is None:
        return None
    return occupancy.get(container_id, {}).get(position)


def remove_from_occupancy(
    occupancy: dict[int, dict[int, int]],
    book_id: int,
) -> None:
    for positions in occupancy.values():
        for position, occupant_id in list(positions.items()):
            if occupant_id == book_id:
                del positions[position]
                return


def remove_active(
    books: dict[int, PlannedBook],
    occupancy: dict[int, dict[int, int]],
    book_id: int,
    mode: OldPositionMode,
    affected: set[int],
) -> int:
    book = books[book_id]
    if book.container_id is None or book.position is None:
        return 0
    container_id = book.container_id
    old_position = book.position
    remove_from_occupancy(occupancy, book_id)
    books[book_id] = replace(book, container_id=None, position=None)
    affected.add(container_id)
    if mode == OldPositionMode.collapse:
        positions = occupancy.setdefault(container_id, {})
        shifted_count = 0
        for position in sorted(
            [position for position in positions if position > old_position]
        ):
            shifted_id = positions.pop(position)
            positions[position - 1] = shifted_id
            books[shifted_id] = replace(books[shifted_id], position=position - 1)
            shifted_count += 1
        return shifted_count
    return 0


def shifted_summary(count: int, reason: str) -> str:
    noun = "book" if count == 1 else "books"
    return f"{count} {noun} shifted {reason}."


def is_single_same_container_move(
    request: RearrangementOperation,
    initial_source: tuple[int | None, int | None],
    step: RearrangementStep,
) -> bool:
    return (
        len(request.steps) == 1
        and initial_source[0] is not None
        and initial_source[0] == step.container_id
    )


def append_net_shift_summary(
    movement_log: list[str],
    original: dict[int, PlannedBook],
    books: dict[int, PlannedBook],
    moving_book_id: int,
) -> None:
    count = sum(
        1
        for book_id, book in books.items()
        if book_id != moving_book_id
        and (book.container_id, book.position)
        != (original[book_id].container_id, original[book_id].position)
    )
    if count:
        movement_log.append(
            shifted_summary(count, "to fill the gap and make new room")
        )


def validate_destination_position(
    occupancy: dict[int, dict[int, int]],
    container_id: int,
    position: int,
) -> None:
    positions = occupancy.get(container_id, {})
    maximum = max(positions, default=0)
    if position > maximum + 1:
        raise HTTPException(
            status_code=422,
            detail="Destination must be an existing slot, a gap, or the next end position",
        )


def squeeze_destination(
    books: dict[int, PlannedBook],
    occupancy: dict[int, dict[int, int]],
    container_id: int,
    position: int,
) -> list[tuple[int, int]]:
    positions = occupancy.setdefault(container_id, {})
    empty = position
    while empty in positions:
        empty += 1
    shifted: list[tuple[int, int]] = []
    for current in range(empty - 1, position - 1, -1):
        shifted_id = positions.pop(current)
        positions[current + 1] = shifted_id
        books[shifted_id] = replace(books[shifted_id], position=current + 1)
        shifted.append((shifted_id, current + 1))
    return list(reversed(shifted))


def place_book(
    books: dict[int, PlannedBook],
    occupancy: dict[int, dict[int, int]],
    book_id: int,
    container_id: int,
    position: int,
) -> None:
    if occupant_at(occupancy, container_id, position) is not None:
        raise HTTPException(status_code=409, detail="Destination remains occupied")
    remove_from_occupancy(occupancy, book_id)
    occupancy.setdefault(container_id, {})[position] = book_id
    books[book_id] = replace(
        books[book_id],
        container_id=container_id,
        position=position,
    )


def container_gaps(
    occupancy: dict[int, dict[int, int]],
    container_ids: set[int],
) -> list[dict[str, Any]]:
    gaps = []
    for container_id in sorted(container_ids):
        positions = occupancy.get(container_id, {})
        maximum = max(positions, default=0)
        missing = [position for position in range(1, maximum + 1) if position not in positions]
        if missing:
            gaps.append({"container_id": container_id, "positions": missing})
    return gaps


def result_payload(
    original: dict[int, PlannedBook],
    books: dict[int, PlannedBook],
    containers: dict[int, str],
    affected: set[int],
    movement_log: list[str],
    warnings: list[str],
    effective_old_mode: OldPositionMode,
    active_id: int | None,
    *,
    complete: bool,
) -> dict[str, Any]:
    occupancy = build_occupancy(books)
    gaps = container_gaps(occupancy, affected)
    placements = [
        {
            "book_id": book.id,
            "container_id": book.container_id,
            "position": book.position,
            "status": book.status,
        }
        for book in books.values()
        if (
            book.container_id,
            book.position,
            book.status,
        )
        != (
            original[book.id].container_id,
            original[book.id].position,
            original[book.id].status,
        )
    ]
    return {
        "revision": rearrangement_revision(original),
        "valid_to_apply": complete and not gaps and bool(placements),
        "complete": complete,
        "effective_old_position_mode": effective_old_mode.value,
        "next_active_book_id": active_id,
        "placements": placements,
        "gaps": gaps,
        "movement_log": movement_log,
        "movement_groups": [movement_log] if movement_log else [],
        "warnings": warnings,
        "_planned_books": books,
    }


def transition_to_reading(book: PlannedBook) -> PlannedBook:
    started = None if book.status == BookStatus.read.value else book.reading_started_date
    if started is None:
        candidates = [date.today()]
        if book.acquisition_date:
            candidates.append(date.fromisoformat(book.acquisition_date))
        started = max(candidates).isoformat()
    return replace(
        book,
        status=BookStatus.currently_reading.value,
        reading_started_date=started,
        read_date=None,
        is_read_date_unknown=False,
    )


def transition_from_reading(book: PlannedBook, status: str) -> PlannedBook:
    if status == BookStatus.pending.value:
        return replace(
            book,
            status=status,
            reading_started_date=None,
            read_date=None,
            is_read_date_unknown=False,
        )
    candidates = [date.today()]
    for value in (
        book.acquisition_date,
        book.reading_started_date,
    ):
        if value:
            candidates.append(date.fromisoformat(value))
    return replace(
        book,
        status=BookStatus.read.value,
        read_date=book.read_date or max(candidates).isoformat(),
        is_read_date_unknown=False,
    )


def position_label(
    containers: dict[int, str],
    container_id: int,
    position: int,
) -> str:
    return f"{containers[container_id]} · Position {position}"


def apply_planned_books(
    connection: sqlite3.Connection,
    original: dict[int, PlannedBook],
    planned: dict[int, PlannedBook],
) -> None:
    changed = [
        book
        for book in planned.values()
        if (
            book.container_id,
            book.position,
            book.status,
            book.reading_started_date,
            book.read_date,
            book.is_read_date_unknown,
        )
        != (
            original[book.id].container_id,
            original[book.id].position,
            original[book.id].status,
            original[book.id].reading_started_date,
            original[book.id].read_date,
            original[book.id].is_read_date_unknown,
        )
    ]
    for book in changed:
        connection.execute(
            "UPDATE books SET container_id = NULL, position = NULL WHERE id = ?",
            (book.id,),
        )
    for book in changed:
        connection.execute(
            """
            UPDATE books
            SET container_id = ?, position = ?, status = ?,
                reading_started_date = ?, read_date = ?,
                is_read_date_unknown = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                book.container_id,
                book.position,
                book.status,
                book.reading_started_date,
                book.read_date,
                int(book.is_read_date_unknown),
                book.id,
            ),
        )
        if book.status != original[book.id].status:
            apply_projected_reading_values(
                connection,
                book.id,
                status=book.status,
                started=(
                    date.fromisoformat(book.reading_started_date)
                    if book.reading_started_date else None
                ),
                finished=(
                    date.fromisoformat(book.read_date) if book.read_date else None
                ),
                dates_unknown=book.is_read_date_unknown,
            )
        else:
            sync_book_projection(connection, book.id)
