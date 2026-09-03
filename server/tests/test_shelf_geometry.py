from uuid import uuid4

import pytest

from bookpile_server.services.shelf_geometry import ShelfGeometryError, ShelfSpec, project_shelves


def shelf(number: int, *, width=None, height=None, open_top=False) -> ShelfSpec:
    return ShelfSpec(uuid4(), number, width, height, open_top=open_top)


def test_vertical_shelves_use_real_furniture_scale_and_residual_bottom() -> None:
    result = project_shelves(
        furniture_width_mm=800, furniture_height_mm=1000,
        direction="TOP_TO_BOTTOM", homogeneous=True,
        frame_left_mm=20, frame_right_mm=20, top_closure_mm=20,
        bottom_closure_mm=20, separator_thickness_mm=20,
        shelves=[shelf(1, height=200), shelf(2, height=300)],
    )
    assert [item.width_mm for item in result] == [760, 760]
    assert [item.height_mm for item in result] == [200, 300]
    assert result[0].floor_y_mm == 780
    assert result[1].floor_y_mm == 460


def test_bottom_to_top_places_first_shelf_at_bottom() -> None:
    result = project_shelves(
        furniture_width_mm=800, furniture_height_mm=1000,
        direction="BOTTOM_TO_TOP", homogeneous=True,
        frame_left_mm=20, frame_right_mm=20, top_closure_mm=20,
        bottom_closure_mm=20, separator_thickness_mm=20,
        shelves=[shelf(1, height=200), shelf(2, height=300)],
    )
    assert result[0].floor_y_mm == 20
    assert result[1].floor_y_mm == 240


def test_horizontal_residual_is_shared_between_separators() -> None:
    result = project_shelves(
        furniture_width_mm=1000, furniture_height_mm=500,
        direction="LEFT_TO_RIGHT", homogeneous=True,
        frame_left_mm=20, frame_right_mm=20, top_closure_mm=20,
        bottom_closure_mm=20, separator_thickness_mm=20,
        shelves=[shelf(1, width=200), shelf(2, width=300)],
    )
    assert result[0].x_mm == 20
    assert result[1].x_mm == 680
    assert result[0].separator_after_mm == 460


def test_fallbacks_compress_but_entered_dimensions_do_not() -> None:
    result = project_shelves(
        furniture_width_mm=800, furniture_height_mm=100,
        direction="TOP_TO_BOTTOM", homogeneous=True,
        frame_left_mm=20, frame_right_mm=20, top_closure_mm=5,
        bottom_closure_mm=5, separator_thickness_mm=5,
        shelves=[shelf(index) for index in range(1, 8)],
    )
    assert all(item.height_mm >= 5 for item in result)
    with pytest.raises(ShelfGeometryError):
        project_shelves(
            furniture_width_mm=800, furniture_height_mm=100,
            direction="TOP_TO_BOTTOM", homogeneous=True,
            frame_left_mm=20, frame_right_mm=20, top_closure_mm=5,
            bottom_closure_mm=5, separator_thickness_mm=5,
            shelves=[shelf(1, height=60), shelf(2, height=60)],
        )


def test_only_top_shelf_can_be_open() -> None:
    common = dict(
        furniture_width_mm=800, furniture_height_mm=1000,
        direction="TOP_TO_BOTTOM", homogeneous=False,
        frame_left_mm=20, frame_right_mm=20, top_closure_mm=20,
        bottom_closure_mm=20, separator_thickness_mm=20,
    )
    result = project_shelves(**common, shelves=[shelf(1, width=800, open_top=True)])
    assert result[0].x_mm == 0
    assert result[0].width_mm == 800
    with pytest.raises(ShelfGeometryError):
        project_shelves(**common, shelves=[shelf(1), shelf(2, open_top=True)])
