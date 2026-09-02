from uuid import uuid4

import pytest

from bookpile_server.services.physical_geometry import (
    BookMeasurement,
    catalogue_dimension_defaults,
    measurement_diagnostics,
    occupied_percentages,
    occupied_size,
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
