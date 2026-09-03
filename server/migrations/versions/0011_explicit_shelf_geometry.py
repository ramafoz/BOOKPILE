"""Add explicit shelf, frame, and separator geometry.

Revision ID: 0011_explicit_shelves
Revises: 0010_unbounded_geometry

The legacy height_weight column is intentionally retained for a safe downgrade.
It no longer governs rendering once the application uses this revision.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0011_explicit_shelves"
down_revision: str | None = "0010_unbounded_geometry"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("visual_bookcase_layouts", sa.Column("shelf_direction", sa.String(24), nullable=True))
    op.add_column("visual_bookcase_layouts", sa.Column("homogeneous_structure", sa.Boolean(), nullable=True))
    for name in ("frame_left_mm", "frame_right_mm", "top_closure_mm", "bottom_closure_mm", "separator_thickness_mm"):
        op.add_column("visual_bookcase_layouts", sa.Column(name, sa.Numeric(14, 4), nullable=True))

    for name in ("x_mm", "floor_y_mm", "width_mm", "height_mm", "offset_mm", "left_frame_mm", "right_frame_mm", "top_closure_mm", "bottom_board_mm", "separator_after_mm", "separator_height_mm"):
        op.add_column("visual_shelf_layouts", sa.Column(name, sa.Numeric(14, 4), nullable=True))
    for name, length in (("alignment", 8), ("width_source", 10), ("height_source", 10), ("separator_anchor", 8), ("separator_source", 10)):
        op.add_column("visual_shelf_layouts", sa.Column(name, sa.String(length), nullable=True))
    op.add_column("visual_shelf_layouts", sa.Column("open_top", sa.Boolean(), nullable=True))

    # Preserve the exact old shelf rectangles. Coordinates are furniture-local,
    # positive-up floor baselines. Structural defaults are recorded separately
    # and are adopted only by an explicit physical refresh.
    op.execute(sa.text("""
        UPDATE visual_bookcase_layouts
        SET shelf_direction = 'TOP_TO_BOTTOM', homogeneous_structure = true,
            frame_left_mm = width_mm * 0.025,
            frame_right_mm = width_mm * 0.025,
            top_closure_mm = height_mm * 0.025,
            bottom_closure_mm = height_mm * 0.025,
            separator_thickness_mm = GREATEST(5, width_mm * 0.025)
    """))
    op.execute(sa.text("""
        WITH ranked AS (
            SELECT v.library_id, v.shelf_id, s.bookcase_id,
                   b.width_mm AS furniture_width,
                   b.height_mm AS furniture_height,
                   v.height_weight,
                   SUM(v.height_weight) OVER (PARTITION BY s.bookcase_id) AS total_weight,
                   COALESCE(SUM(v.height_weight) OVER (
                       PARTITION BY s.bookcase_id ORDER BY s.shelf_number, s.id
                       ROWS BETWEEN UNBOUNDED PRECEDING AND 1 PRECEDING
                   ), 0) AS preceding_weight,
                   ROW_NUMBER() OVER (PARTITION BY s.bookcase_id ORDER BY s.shelf_number DESC, s.id DESC) AS reverse_rank
            FROM visual_shelf_layouts v
            JOIN shelves s ON s.library_id = v.library_id AND s.id = v.shelf_id
            JOIN visual_bookcase_layouts b ON b.library_id = s.library_id AND b.bookcase_id = s.bookcase_id
        )
        UPDATE visual_shelf_layouts v
        SET x_mm = r.furniture_width * 0.025,
            width_mm = r.furniture_width * 0.95,
            height_mm = r.furniture_height * 0.95 * r.height_weight / NULLIF(r.total_weight, 0),
            floor_y_mm = r.furniture_height * 0.975
                - r.furniture_height * 0.95 * (r.preceding_weight + r.height_weight) / NULLIF(r.total_weight, 0),
            alignment = 'CENTER', offset_mm = 0,
            width_source = 'DERIVED', height_source = 'DERIVED', open_top = false,
            left_frame_mm = r.furniture_width * 0.025,
            right_frame_mm = r.furniture_width * 0.025,
            top_closure_mm = r.furniture_height * 0.025,
            bottom_board_mm = r.furniture_height * 0.025,
            separator_after_mm = CASE WHEN r.reverse_rank > 1 THEN 5 ELSE NULL END,
            separator_anchor = 'BOTTOM',
            separator_height_mm = CASE WHEN r.reverse_rank > 1 THEN r.furniture_height * 0.95 ELSE NULL END,
            separator_source = CASE WHEN r.reverse_rank > 1 THEN 'FALLBACK' ELSE NULL END
        FROM ranked r
        WHERE v.library_id = r.library_id AND v.shelf_id = r.shelf_id
    """))

    for table, columns in (
        ("visual_bookcase_layouts", ("shelf_direction", "homogeneous_structure", "frame_left_mm", "frame_right_mm", "top_closure_mm", "bottom_closure_mm", "separator_thickness_mm")),
        ("visual_shelf_layouts", ("x_mm", "floor_y_mm", "width_mm", "height_mm", "alignment", "offset_mm", "width_source", "height_source", "open_top", "left_frame_mm", "right_frame_mm", "top_closure_mm", "bottom_board_mm", "separator_anchor")),
    ):
        for column in columns:
            op.alter_column(table, column, nullable=False)

    op.create_check_constraint("ck_visual_bookcase_shelf_direction", "visual_bookcase_layouts", "shelf_direction IN ('TOP_TO_BOTTOM','BOTTOM_TO_TOP','LEFT_TO_RIGHT','RIGHT_TO_LEFT')")
    op.create_check_constraint("ck_visual_bookcase_structure_nonnegative", "visual_bookcase_layouts", "frame_left_mm >= 0 AND frame_right_mm >= 0 AND top_closure_mm >= 0 AND bottom_closure_mm >= 0 AND separator_thickness_mm >= 5")
    op.create_check_constraint("ck_visual_shelf_size_positive", "visual_shelf_layouts", "width_mm > 0 AND height_mm > 0")
    op.create_check_constraint("ck_visual_shelf_frames_nonnegative", "visual_shelf_layouts", "left_frame_mm >= 0 AND right_frame_mm >= 0 AND top_closure_mm >= 0 AND bottom_board_mm >= 0")
    op.create_check_constraint("ck_visual_shelf_alignment", "visual_shelf_layouts", "alignment IN ('LEFT','CENTER','RIGHT')")
    op.create_check_constraint("ck_visual_shelf_sources", "visual_shelf_layouts", "width_source IN ('ENTERED','FALLBACK','DERIVED') AND height_source IN ('ENTERED','FALLBACK','DERIVED')")
    op.create_check_constraint("ck_visual_shelf_separator", "visual_shelf_layouts", "separator_anchor IN ('TOP','BOTTOM') AND (separator_after_mm IS NULL OR separator_after_mm >= 5) AND (separator_height_mm IS NULL OR separator_height_mm >= 5) AND (separator_source IS NULL OR separator_source IN ('ENTERED','FALLBACK','DERIVED'))")


def downgrade() -> None:
    for name in ("ck_visual_shelf_separator", "ck_visual_shelf_sources", "ck_visual_shelf_alignment", "ck_visual_shelf_frames_nonnegative", "ck_visual_shelf_size_positive"):
        op.drop_constraint(name, "visual_shelf_layouts", type_="check")
    for name in ("ck_visual_bookcase_structure_nonnegative", "ck_visual_bookcase_shelf_direction"):
        op.drop_constraint(name, "visual_bookcase_layouts", type_="check")
    for name in ("separator_source", "separator_height_mm", "separator_after_mm", "separator_anchor", "bottom_board_mm", "top_closure_mm", "right_frame_mm", "left_frame_mm", "open_top", "height_source", "width_source", "offset_mm", "alignment", "height_mm", "width_mm", "floor_y_mm", "x_mm"):
        op.drop_column("visual_shelf_layouts", name)
    for name in ("separator_thickness_mm", "bottom_closure_mm", "top_closure_mm", "frame_right_mm", "frame_left_mm", "homogeneous_structure", "shelf_direction"):
        op.drop_column("visual_bookcase_layouts", name)
