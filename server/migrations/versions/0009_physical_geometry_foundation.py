"""Add the canonical physical-geometry foundation.

Revision ID: 0009_physical_geometry
Revises: 0008_private_book_covers
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0009_physical_geometry"
down_revision: str | None = "0008_private_book_covers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "libraries",
        sa.Column("geometry_mode", sa.String(length=16), server_default="MANUAL", nullable=False),
    )
    op.add_column(
        "libraries",
        sa.Column("coordinate_system_version", sa.Integer(), server_default="2", nullable=False),
    )
    op.create_check_constraint(
        "ck_libraries_geometry_mode",
        "libraries",
        "geometry_mode IN ('MANUAL', 'PHYSICAL')",
    )
    op.create_check_constraint(
        "ck_libraries_coordinate_system_version",
        "libraries",
        "coordinate_system_version >= 2",
    )

    op.alter_column("visual_bookcase_layouts", "x", new_column_name="x_mm")
    op.alter_column("visual_bookcase_layouts", "y", new_column_name="floor_y_mm")
    op.alter_column("visual_bookcase_layouts", "width", new_column_name="width_mm")
    op.alter_column("visual_bookcase_layouts", "height", new_column_name="height_mm")
    op.execute(
        "UPDATE visual_bookcase_layouts "
        "SET x_mm = x_mm * 20, "
        "floor_y_mm = (floor_y_mm + height_mm) * 20, "
        "width_mm = width_mm * 20, height_mm = height_mm * 20"
    )

    op.alter_column("visual_outside_areas", "x", new_column_name="x_mm")
    op.alter_column("visual_outside_areas", "y", new_column_name="y_mm")
    op.alter_column("visual_outside_areas", "width", new_column_name="width_mm")
    op.alter_column("visual_outside_areas", "height", new_column_name="height_mm")
    op.execute(
        "UPDATE visual_outside_areas SET "
        "x_mm = x_mm * 20, y_mm = y_mm * 20, "
        "width_mm = width_mm * 20, height_mm = height_mm * 20"
    )

    op.drop_constraint(
        "fk_visual_container_library_support",
        "visual_container_layouts",
        type_="foreignkey",
    )
    for name in (
        "ck_visual_container_support_kind",
        "ck_visual_container_support_pair",
        "ck_visual_container_not_self_supported",
    ):
        op.drop_constraint(name, "visual_container_layouts", type_="check")
    op.alter_column(
        "visual_container_layouts",
        "pile_support_kind",
        new_column_name="support_kind",
        type_=sa.String(length=16),
        existing_type=sa.String(length=8),
    )
    op.alter_column(
        "visual_container_layouts",
        "pile_support_container_id",
        new_column_name="support_container_id",
    )
    op.execute(
        "UPDATE visual_container_layouts SET "
        "support_kind = CASE WHEN support_kind = 'ROW' THEN 'CONTAINER' "
        "ELSE COALESCE(support_kind, 'SHELF') END"
    )
    op.add_column(
        "visual_container_layouts",
        sa.Column("pile_alignment", sa.String(length=8), server_default="RIGHT", nullable=False),
    )
    op.create_check_constraint(
        "ck_visual_container_support_kind",
        "visual_container_layouts",
        "support_kind IN ('SHELF', 'CONTAINER')",
    )
    op.create_check_constraint(
        "ck_visual_container_support_pair",
        "visual_container_layouts",
        "(support_kind = 'SHELF' AND support_container_id IS NULL) OR "
        "(support_kind = 'CONTAINER' AND support_container_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_visual_container_not_self_supported",
        "visual_container_layouts",
        "support_container_id IS NULL OR support_container_id <> container_id",
    )
    op.create_check_constraint(
        "ck_visual_container_pile_alignment",
        "visual_container_layouts",
        "pile_alignment IN ('LEFT', 'CENTER', 'RIGHT')",
    )
    op.create_foreign_key(
        "fk_visual_container_library_support",
        "visual_container_layouts",
        "containers",
        ["library_id", "support_container_id"],
        ["library_id", "id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_visual_container_library_support",
        "visual_container_layouts",
        type_="foreignkey",
    )
    for name in (
        "ck_visual_container_pile_alignment",
        "ck_visual_container_not_self_supported",
        "ck_visual_container_support_pair",
        "ck_visual_container_support_kind",
    ):
        op.drop_constraint(name, "visual_container_layouts", type_="check")
    op.execute(
        "UPDATE visual_container_layouts AS layout SET "
        "support_kind = NULL, support_container_id = NULL "
        "FROM containers AS dependent "
        "WHERE dependent.id = layout.container_id "
        "AND dependent.library_id = layout.library_id "
        "AND dependent.container_type = 'ROW'"
    )
    op.execute(
        "UPDATE visual_container_layouts AS layout SET "
        "support_kind = 'SHELF', support_container_id = NULL "
        "WHERE support_kind = 'CONTAINER' AND NOT EXISTS ("
        "SELECT 1 FROM containers AS support "
        "WHERE support.id = layout.support_container_id "
        "AND support.library_id = layout.library_id "
        "AND support.container_type = 'ROW')"
    )
    op.execute(
        "UPDATE visual_container_layouts SET support_kind = 'ROW' "
        "WHERE support_kind = 'CONTAINER'"
    )
    op.drop_column("visual_container_layouts", "pile_alignment")
    op.alter_column(
        "visual_container_layouts",
        "support_kind",
        new_column_name="pile_support_kind",
        type_=sa.String(length=8),
        existing_type=sa.String(length=16),
    )
    op.alter_column(
        "visual_container_layouts",
        "support_container_id",
        new_column_name="pile_support_container_id",
    )
    op.create_check_constraint(
        "ck_visual_container_support_kind",
        "visual_container_layouts",
        "pile_support_kind IS NULL OR pile_support_kind IN ('SHELF', 'ROW')",
    )
    op.create_check_constraint(
        "ck_visual_container_support_pair",
        "visual_container_layouts",
        "(pile_support_kind IS NULL AND pile_support_container_id IS NULL) OR "
        "(pile_support_kind = 'SHELF' AND pile_support_container_id IS NULL) OR "
        "(pile_support_kind = 'ROW' AND pile_support_container_id IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_visual_container_not_self_supported",
        "visual_container_layouts",
        "pile_support_container_id IS NULL OR pile_support_container_id <> container_id",
    )
    op.create_foreign_key(
        "fk_visual_container_library_support",
        "visual_container_layouts",
        "containers",
        ["library_id", "pile_support_container_id"],
        ["library_id", "id"],
        ondelete="RESTRICT",
    )

    op.execute(
        "UPDATE visual_outside_areas SET "
        "x_mm = x_mm / 20, y_mm = y_mm / 20, "
        "width_mm = width_mm / 20, height_mm = height_mm / 20"
    )
    op.alter_column("visual_outside_areas", "x_mm", new_column_name="x")
    op.alter_column("visual_outside_areas", "y_mm", new_column_name="y")
    op.alter_column("visual_outside_areas", "width_mm", new_column_name="width")
    op.alter_column("visual_outside_areas", "height_mm", new_column_name="height")

    op.execute(
        "UPDATE visual_bookcase_layouts SET "
        "x_mm = x_mm / 20, "
        "floor_y_mm = (floor_y_mm - height_mm) / 20, "
        "width_mm = width_mm / 20, height_mm = height_mm / 20"
    )
    op.alter_column("visual_bookcase_layouts", "x_mm", new_column_name="x")
    op.alter_column("visual_bookcase_layouts", "floor_y_mm", new_column_name="y")
    op.alter_column("visual_bookcase_layouts", "width_mm", new_column_name="width")
    op.alter_column("visual_bookcase_layouts", "height_mm", new_column_name="height")

    op.drop_constraint("ck_libraries_coordinate_system_version", "libraries", type_="check")
    op.drop_constraint("ck_libraries_geometry_mode", "libraries", type_="check")
    op.drop_column("libraries", "coordinate_system_version")
    op.drop_column("libraries", "geometry_mode")
