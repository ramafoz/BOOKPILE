from uuid import uuid4

from bookpile_server.schemas import RearrangementOperationWrite, RearrangementRequest
from bookpile_server.services.rearrangement import (
    PlannedBook,
    PlannedContainer,
    plan,
)


def container(*, x: float, width: float, label: str) -> PlannedContainer:
    return PlannedContainer(
        id=uuid4(),
        shelf_id=SHELF_ID,
        label=label,
        kind="ROW",
        layer="BACKGROUND",
        x=x,
        y=10,
        width=width,
        height=50,
        row_anchor="LEFT",
        support_kind="SHELF",
        support_container_id=None,
        pile_alignment="RIGHT",
    )


def book(container_id, position: int, title: str, pages: int = 100) -> PlannedBook:
    return PlannedBook(
        id=uuid4(),
        title=title,
        author="Author",
        page_count=pages,
        container_id=container_id,
        position=position,
    )


SHELF_ID = uuid4()


def positions(result, container_id):
    return {
        item.title: item.position
        for item in result.books.values()
        if item.container_id == container_id
    }


def test_same_container_collapse_and_squeeze_keeps_a_continuous_sequence():
    row = container(x=0, width=60, label="Shelf 1 · Row 1")
    first = book(row.id, 1, "First")
    second = book(row.id, 2, "Second")
    third = book(row.id, 3, "Third")

    result = plan(
        {item.id: item for item in (first, second, third)},
        {row.id: row},
        RearrangementRequest(
            book_id=first.id,
            steps=[{"container_id": row.id, "position": 3}],
        ),
    )

    assert result.payload["valid_to_apply"] is True
    assert positions(result, row.id) == {"Second": 1, "Third": 2, "First": 3}
    assert result.payload["gaps"] == []


def test_continue_chain_fills_the_original_gap():
    source = container(x=0, width=40, label="Shelf 1 · Row 1")
    destination = container(x=50, width=40, label="Shelf 1 · Row 2")
    moving = book(source.id, 1, "Moving")
    displaced = book(destination.id, 1, "Displaced")

    result = plan(
        {item.id: item for item in (moving, displaced)},
        {source.id: source, destination.id: destination},
        RearrangementRequest(
            book_id=moving.id,
            old_position_mode="LEAVE_GAP",
            steps=[
                {
                    "container_id": destination.id,
                    "position": 1,
                    "new_position_mode": "CONTINUE",
                },
                {
                    "container_id": source.id,
                    "position": 1,
                    "new_position_mode": "SQUEEZE",
                },
            ],
        ),
    )

    assert result.payload["valid_to_apply"] is True
    assert positions(result, source.id) == {"Displaced": 1}
    assert positions(result, destination.id) == {"Moving": 1}


def test_cross_container_move_resizes_source_and_destination_by_page_share():
    source = container(x=0, width=40, label="Shelf 1 · Row 1")
    destination = container(x=50, width=20, label="Shelf 1 · Row 2")
    moving = book(source.id, 1, "Moving")
    remaining = book(source.id, 2, "Remaining")
    existing = book(destination.id, 1, "Existing")

    result = plan(
        {item.id: item for item in (moving, remaining, existing)},
        {source.id: source, destination.id: destination},
        RearrangementRequest(
            book_id=moving.id,
            release_shelf_space=True,
            steps=[{"container_id": destination.id, "position": 1}],
        ),
    )

    assert result.payload["valid_to_apply"] is True
    layouts = {item["container_id"]: item for item in result.payload["container_layouts"]}
    assert layouts[source.id]["width"] == 20
    assert layouts[destination.id]["width"] == 40


def test_completed_operation_can_be_followed_by_another_operation():
    row = container(x=0, width=60, label="Shelf 1 · Row 1")
    first = book(row.id, 1, "First")
    second = book(row.id, 2, "Second")
    third = book(row.id, 3, "Third")
    completed = RearrangementOperationWrite(
        book_id=first.id,
        steps=[{"container_id": row.id, "position": 3}],
    )

    result = plan(
        {item.id: item for item in (first, second, third)},
        {row.id: row},
        RearrangementRequest(
            book_id=second.id,
            steps=[{"container_id": row.id, "position": 3}],
            completed_operations=[completed],
        ),
    )

    assert result.payload["valid_to_apply"] is True
    assert len(result.payload["movement_groups"]) == 2
    assert positions(result, row.id) == {"Third": 1, "First": 2, "Second": 3}
