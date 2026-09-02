"""Allow truthful physical container geometry outside shelf bounds.

Revision ID: 0010_unbounded_geometry
Revises: 0009_physical_geometry
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0010_unbounded_geometry"
down_revision: str | None = "0009_physical_geometry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_BOUND_CONSTRAINTS = (
    "ck_visual_container_x",
    "ck_visual_container_y",
    "ck_visual_container_width",
    "ck_visual_container_height",
)


def upgrade() -> None:
    for name in _BOUND_CONSTRAINTS:
        op.drop_constraint(name, "visual_container_layouts", type_="check")
    for column in ("x", "y", "width", "height"):
        op.alter_column(
            "visual_container_layouts",
            column,
            type_=sa.Numeric(14, 4),
            existing_type=sa.Numeric(7, 4),
            existing_nullable=False,
        )
    op.create_check_constraint(
        "ck_visual_container_width_positive",
        "visual_container_layouts",
        "width > 0",
    )
    op.create_check_constraint(
        "ck_visual_container_height_positive",
        "visual_container_layouts",
        "height > 0",
    )


def downgrade() -> None:
    connection = op.get_bind()
    incompatible = connection.scalar(sa.text(
        "SELECT count(*) FROM visual_container_layouts "
        "WHERE x < 0 OR y < 0 OR width <= 0 OR height <= 0 "
        "OR x + width > 100 OR y + height > 100"
    ))
    if incompatible:
        raise RuntimeError(
            "Cannot downgrade while physical container geometry extends outside a shelf."
        )
    op.drop_constraint(
        "ck_visual_container_height_positive",
        "visual_container_layouts",
        type_="check",
    )
    op.drop_constraint(
        "ck_visual_container_width_positive",
        "visual_container_layouts",
        type_="check",
    )
    for column in ("x", "y", "width", "height"):
        op.alter_column(
            "visual_container_layouts",
            column,
            type_=sa.Numeric(7, 4),
            existing_type=sa.Numeric(14, 4),
            existing_nullable=False,
        )
    op.create_check_constraint(
        "ck_visual_container_x", "visual_container_layouts", "x >= 0 AND x <= 100"
    )
    op.create_check_constraint(
        "ck_visual_container_y", "visual_container_layouts", "y >= 0 AND y <= 100"
    )
    op.create_check_constraint(
        "ck_visual_container_width",
        "visual_container_layouts",
        "width > 0 AND width <= 100 AND x + width <= 100",
    )
    op.create_check_constraint(
        "ck_visual_container_height",
        "visual_container_layouts",
        "height > 0 AND height <= 100 AND y + height <= 100",
    )
