from __future__ import annotations

import pytest

from app.visual_geometry import (
    AuditContainer,
    CapacityState,
    ContainerKind,
    LEGACY_SUPPORT_TOLERANCE,
    Rect,
    RowAnchor,
    SupportKind,
    apply_axis_span,
    effective_page_count,
    effective_page_mean,
    infer_pile_support,
    is_full,
    page_count_warning,
    project_occupied_span,
    proportional_segments,
)


def container(
    identifier: int,
    kind: ContainerKind,
    rect: Rect,
    *,
    shelf: int = 1,
    layer: str = "BACKGROUND",
    books: int = 1,
) -> AuditContainer:
    return AuditContainer(identifier, shelf, layer, kind, rect, books)


def test_effective_pages_use_valid_arithmetic_mean_and_fallback() -> None:
    assert effective_page_mean([100, None, 0, -2, 300]) == 200
    assert effective_page_mean([None, 0]) == 200
    assert effective_page_count(None, 250) == 250
    assert effective_page_count(144, 250) == 144


def test_segments_are_strictly_page_proportional_and_fill_exact_span() -> None:
    segments = proportional_segments(100, [100, 300, None], 200)
    assert [segment.offset for segment in segments] == pytest.approx([0, 100 / 6, 400 / 6])
    assert [segment.thickness for segment in segments] == pytest.approx([100 / 6, 300 / 6, 200 / 6])
    assert segments[-1].offset + segments[-1].thickness == pytest.approx(100)


def test_pile_support_is_same_shelf_same_layer_non_empty_row_only() -> None:
    pile = container(10, ContainerKind.PILE, Rect(20, 10, 20, 30))
    valid = container(20, ContainerKind.ROW, Rect(10, 40, 50, 20))
    wrong_layer = container(21, ContainerKind.ROW, Rect(10, 40, 50, 20), layer="FOREGROUND")
    empty = container(22, ContainerKind.ROW, Rect(10, 40, 50, 20), books=0)
    result = infer_pile_support(pile, [pile, valid, wrong_layer, empty])
    assert result.kind is SupportKind.ROW
    assert result.container_id == valid.id


def test_pile_on_shelf_wins_and_multiple_rows_are_ambiguous() -> None:
    shelf_pile = container(1, ContainerKind.PILE, Rect(0, 60, 20, 40))
    assert infer_pile_support(shelf_pile, [shelf_pile]).kind is SupportKind.SHELF

    pile = container(2, ContainerKind.PILE, Rect(20, 10, 20, 30))
    rows = [
        container(3, ContainerKind.ROW, Rect(0, 40, 30, 20)),
        container(4, ContainerKind.ROW, Rect(25, 40, 30, 20)),
    ]
    result = infer_pile_support(pile, [pile, *rows])
    assert result.kind is SupportKind.AMBIGUOUS
    assert result.candidates == (3, 4)


def test_touching_without_positive_horizontal_overlap_is_not_support() -> None:
    pile = container(1, ContainerKind.PILE, Rect(0, 10, 20, 30))
    row = container(2, ContainerKind.ROW, Rect(20, 40, 30, 20))
    assert infer_pile_support(pile, [pile, row]).kind is SupportKind.INVALID


def test_legacy_support_tolerance_absorbs_old_manual_layout_gaps() -> None:
    pile = container(1, ContainerKind.PILE, Rect(10, 0, 20, 27.8))
    row = container(2, ContainerKind.ROW, Rect(0, 30, 100, 70))
    strict = infer_pile_support(pile, [pile, row])
    legacy = infer_pile_support(pile, [pile, row], LEGACY_SUPPORT_TOLERANCE)
    assert strict.kind is SupportKind.INVALID
    assert legacy.kind is SupportKind.ROW


def test_full_tolerance_and_five_percent_compression_contract() -> None:
    assert is_full(99.9, 100)
    assert not is_full(99.8, 100)

    compressed = project_occupied_span(
        current_span=50, current_pages=100, final_pages=210, capacity=100
    )
    assert compressed.state is CapacityState.COMPRESSED
    assert compressed.span == 100
    assert compressed.compression_ratio == pytest.approx(1 / 21)

    invalid = project_occupied_span(
        current_span=50, current_pages=100, final_pages=211, capacity=100
    )
    assert invalid.state is CapacityState.INVALID


def test_full_container_stays_full_until_release_or_large_reduction() -> None:
    retained = project_occupied_span(
        current_span=100, current_pages=1000, final_pages=960, capacity=100
    )
    released = project_occupied_span(
        current_span=100,
        current_pages=1000,
        final_pages=960,
        capacity=100,
        release_space=True,
    )
    reduced = project_occupied_span(
        current_span=100, current_pages=1000, final_pages=940, capacity=100
    )
    assert retained.span == 100
    assert released.span == 96
    assert reduced.span == 94


def test_axis_resize_preserves_row_anchor_and_pile_bottom() -> None:
    rect = Rect(20, 30, 50, 40)
    assert apply_axis_span(rect, ContainerKind.ROW, 30, RowAnchor.LEFT) == Rect(20, 30, 30, 40)
    assert apply_axis_span(rect, ContainerKind.ROW, 30, RowAnchor.RIGHT) == Rect(40, 30, 30, 40)
    assert apply_axis_span(rect, ContainerKind.PILE, 25) == Rect(20, 45, 50, 25)


def test_page_warning_uses_final_container_share() -> None:
    assert page_count_warning(2001, 10000)
    assert page_count_warning(600, 1000)
    assert not page_count_warning(500, 1000)
    assert not page_count_warning(None, 1000)
