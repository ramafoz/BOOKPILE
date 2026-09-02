from uuid import uuid4

import pytest

from bookpile_server.services.physical_geometry import (
    BookMeasurement,
    ContainerProjectionInput,
    catalogue_dimension_defaults,
    measurement_diagnostics,
    occupied_percentages,
    occupied_size,
    project_containers,
    resolve_book_measurement,
)


def test_resolves_each_axis_independently_with_page_ratio_before_median() -> None:
    measured = BookMeasurement(
        uuid4(), page_count=200, height_mm=240, width_mm=160, thickness_mm=20
    )
    partial = BookMeasurement(uuid4(), page_count=300, height_mm=230)
    defaults = catalogue_dimension_defaults([measured, partial])

    resolved = resolve_book_measurement(partial, defaults)

    assert resolved.height.mm == 230
    assert resolved.height.source == "MEASURED"
    assert resolved.width.mm == 160
    assert resolved.width.source == "CATALOGUE_MEDIAN"
    assert resolved.thickness.mm == pytest.approx(30)
    assert resolved.thickness.source == "PAGE_RATIO"


def test_final_defaults_are_stable_when_catalogue_has_no_measurements() -> None:
    book = BookMeasurement(uuid4())
    resolved = resolve_book_measurement(book, catalogue_dimension_defaults([book]))

    assert (resolved.thickness.mm, resolved.height.mm, resolved.width.mm) == (
        20,
        220,
        150,
    )


def test_row_and_pile_use_the_approved_physical_axes() -> None:
    books = [
        BookMeasurement(uuid4(), 100, 200, 140, 10),
        BookMeasurement(uuid4(), 200, 240, 160, 20),
    ]
    defaults = catalogue_dimension_defaults(books)
    resolved = [resolve_book_measurement(book, defaults) for book in books]

    row_size = occupied_size("ROW", resolved)
    pile_size = occupied_size("PILE", resolved)
    assert (row_size.width_mm, row_size.height_mm) == (30, 240)
    assert (pile_size.width_mm, pile_size.height_mm) == (240, 30)
    assert occupied_percentages(
        occupied_size("ROW", resolved),
        shelf_width_mm=600,
        shelf_height_mm=300,
    ) == (5, 80)


def test_suspicious_measurements_create_derived_warnings_not_stored_state() -> None:
    book = BookMeasurement(uuid4(), 100, 2100, 150, 60)
    resolved = resolve_book_measurement(book, catalogue_dimension_defaults([book]))

    diagnostics = measurement_diagnostics(
        book, resolved, occupied_axis_mm=100
    )

    assert {item.code for item in diagnostics} == {
        "OVERSIZED_MEASUREMENT",
        "LARGE_RELATIVE_THICKNESS",
    }


def test_physical_projection_preserves_anchor_and_places_supported_pile() -> None:
    row_id, pile_id, shelf_id = uuid4(), uuid4(), uuid4()
    books = [BookMeasurement(uuid4(), 200, 240, 160, 20)]
    resolved = tuple(resolve_book_measurement(item, catalogue_dimension_defaults(books)) for item in books)
    projected, diagnostics = project_containers([
        ContainerProjectionInput(row_id, shelf_id, "ROW", "BACKGROUND", 20, 40, 50, 60, "RIGHT", None, "RIGHT", 500, 300, resolved),
        ContainerProjectionInput(pile_id, shelf_id, "PILE", "BACKGROUND", 50, 0, 20, 20, "LEFT", row_id, "RIGHT", 500, 300, resolved),
    ])

    assert projected[row_id].x + projected[row_id].width == pytest.approx(70)
    assert projected[row_id].width == pytest.approx(4)
    assert projected[row_id].height == pytest.approx(80)
    assert projected[pile_id].y + projected[pile_id].height == pytest.approx(projected[row_id].y)
    assert diagnostics == []


def test_physical_projection_warns_when_truthful_size_cannot_fit() -> None:
    container_id, shelf_id = uuid4(), uuid4()
    book = BookMeasurement(uuid4(), 100, 400, 200, 600)
    resolved = (resolve_book_measurement(book, catalogue_dimension_defaults([book])),)
    projected, diagnostics = project_containers([
        ContainerProjectionInput(container_id, shelf_id, "ROW", "BACKGROUND", 0, 0, 100, 100, "LEFT", None, "RIGHT", 500, 300, resolved),
    ])

    assert projected[container_id].width == pytest.approx(120)
    assert {item.code for item in diagnostics} == {"OUTSIDE_SHELF"}


def test_physical_projection_warns_when_alignment_places_a_pile_outside() -> None:
    container_id, shelf_id = uuid4(), uuid4()
    book = BookMeasurement(uuid4(), 100, 240, 160, 20)
    resolved = (resolve_book_measurement(book, catalogue_dimension_defaults([book])),)
    projected, diagnostics = project_containers([
        ContainerProjectionInput(
            container_id, shelf_id, "PILE", "FOREGROUND",
            -24, 0, 48, 20, "LEFT", None, "CENTER", 500, 300, resolved,
        ),
    ])

    assert projected[container_id].x < 0
    assert {item.code for item in diagnostics} == {"OUTSIDE_SHELF"}
