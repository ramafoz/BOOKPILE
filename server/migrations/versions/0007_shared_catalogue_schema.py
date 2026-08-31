"""Add the shared catalogue, contributors, hierarchy, and visual layout.

Revision ID: 0007_shared_catalogue_schema
Revises: 0006_library_memberships
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0007_shared_catalogue_schema"
down_revision: str | None = "0006_library_memberships"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


CONTRIBUTOR_ROLES = (
    ("AUTHOR", "Author"),
    ("SCRIPTWRITER", "Scriptwriter"),
    ("TRANSLATOR", "Translator"),
    ("ILLUSTRATOR", "Illustrator"),
    ("PENCILLER", "Penciller"),
    ("INKER", "Inker"),
    ("COLORIST", "Colorist"),
    ("LETTERER", "Letterer"),
    ("COVER_ARTIST", "Cover artist"),
    ("EDITOR", "Editor"),
    ("COORDINATOR", "Coordinator"),
    ("COMPILER", "Compiler"),
    ("PHOTOGRAPHER", "Photographer"),
    ("ADAPTER", "Adapter"),
    ("OTHER", "Other"),
)


def _create_contributor_roles() -> None:
    op.create_table(
        "contributor_roles",
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("label", sa.String(length=80), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "is_active", sa.Boolean(), server_default="true", nullable=False
        ),
        sa.CheckConstraint(
            "length(trim(code)) > 0", name="ck_contributor_roles_code"
        ),
        sa.CheckConstraint(
            "length(trim(label)) > 0", name="ck_contributor_roles_label"
        ),
        sa.CheckConstraint(
            "sort_order > 0", name="ck_contributor_roles_sort_order"
        ),
        sa.PrimaryKeyConstraint("code"),
    )
    role_table = sa.table(
        "contributor_roles",
        sa.column("code", sa.String()),
        sa.column("label", sa.String()),
        sa.column("sort_order", sa.Integer()),
        sa.column("is_active", sa.Boolean()),
    )
    op.bulk_insert(
        role_table,
        [
            {
                "code": code,
                "label": label,
                "sort_order": position,
                "is_active": True,
            }
            for position, (code, label) in enumerate(CONTRIBUTOR_ROLES, start=1)
        ],
    )


def _create_physical_hierarchy() -> None:
    op.create_table(
        "bookcases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("depth_mm", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 160", name="ck_bookcases_name"
        ),
        sa.CheckConstraint(
            "height_mm IS NULL OR height_mm > 0",
            name="ck_bookcases_height_mm",
        ),
        sa.CheckConstraint(
            "width_mm IS NULL OR width_mm > 0", name="ck_bookcases_width_mm"
        ),
        sa.CheckConstraint(
            "depth_mm IS NULL OR depth_mm > 0", name="ck_bookcases_depth_mm"
        ),
        sa.ForeignKeyConstraint(
            ["library_id"], ["libraries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "library_id", "id", name="uq_bookcases_library_id"
        ),
        sa.UniqueConstraint(
            "library_id", "name", name="uq_bookcases_library_name"
        ),
    )
    op.create_index("ix_bookcases_library_id", "bookcases", ["library_id"])

    op.create_table(
        "shelves",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("bookcase_id", sa.Uuid(), nullable=False),
        sa.Column("shelf_number", sa.Integer(), nullable=False),
        sa.Column("usable_height_mm", sa.Integer(), nullable=True),
        sa.Column("usable_width_mm", sa.Integer(), nullable=True),
        sa.Column("usable_depth_mm", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint("shelf_number > 0", name="ck_shelves_number"),
        sa.CheckConstraint(
            "usable_height_mm IS NULL OR usable_height_mm > 0",
            name="ck_shelves_usable_height_mm",
        ),
        sa.CheckConstraint(
            "usable_width_mm IS NULL OR usable_width_mm > 0",
            name="ck_shelves_usable_width_mm",
        ),
        sa.CheckConstraint(
            "usable_depth_mm IS NULL OR usable_depth_mm > 0",
            name="ck_shelves_usable_depth_mm",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "bookcase_id"],
            ["bookcases.library_id", "bookcases.id"],
            name="fk_shelves_library_bookcase",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("library_id", "id", name="uq_shelves_library_id"),
        sa.UniqueConstraint(
            "bookcase_id", "shelf_number", name="uq_shelves_bookcase_number"
        ),
    )
    op.create_index(
        "ix_shelves_library_bookcase", "shelves", ["library_id", "bookcase_id"]
    )

    op.create_table(
        "containers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("shelf_id", sa.Uuid(), nullable=False),
        sa.Column("container_type", sa.String(length=8), nullable=False),
        sa.Column("layer", sa.String(length=16), nullable=False),
        sa.Column("container_number", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "container_type IN ('ROW', 'PILE')", name="ck_containers_type"
        ),
        sa.CheckConstraint(
            "layer IN ('BACKGROUND', 'FOREGROUND')", name="ck_containers_layer"
        ),
        sa.CheckConstraint(
            "container_number > 0", name="ck_containers_number"
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "shelf_id"],
            ["shelves.library_id", "shelves.id"],
            name="fk_containers_library_shelf",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "library_id", "id", name="uq_containers_library_id"
        ),
        sa.UniqueConstraint(
            "shelf_id",
            "container_type",
            "layer",
            "container_number",
            name="uq_containers_shelf_identity",
        ),
    )
    op.create_index(
        "ix_containers_library_shelf",
        "containers",
        ["library_id", "shelf_id"],
    )


def _expand_books() -> None:
    columns = (
        sa.Column("isbn_10", sa.String(length=10), nullable=True),
        sa.Column("isbn_13", sa.String(length=13), nullable=True),
        sa.Column("subtitle", sa.String(length=500), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("publisher", sa.String(length=300), nullable=True),
        sa.Column("current_ed_year", sa.Integer(), nullable=True),
        sa.Column("original_publication_year", sa.Integer(), nullable=True),
        sa.Column("language", sa.String(length=200), nullable=True),
        sa.Column("original_language", sa.String(length=200), nullable=True),
        sa.Column(
            "translation_status",
            sa.String(length=16),
            server_default="UNKNOWN",
            nullable=False,
        ),
        sa.Column("edition_number", sa.Integer(), nullable=True),
        sa.Column("fiction_category", sa.String(length=16), nullable=True),
        sa.Column("binding", sa.String(length=32), nullable=True),
        sa.Column("publication_type", sa.String(length=48), nullable=True),
        sa.Column("genre_text", sa.String(length=1000), nullable=True),
        sa.Column("series_name", sa.String(length=300), nullable=True),
        sa.Column("series_volume", sa.String(length=100), nullable=True),
        sa.Column("goodreads_url", sa.String(length=2048), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("acquisition_date", sa.Date(), nullable=True),
        sa.Column(
            "is_original_collection",
            sa.Boolean(),
            server_default="false",
            nullable=False,
        ),
        sa.Column("height_mm", sa.Integer(), nullable=True),
        sa.Column("width_mm", sa.Integer(), nullable=True),
        sa.Column("thickness_mm", sa.Integer(), nullable=True),
        sa.Column("container_id", sa.Uuid(), nullable=True),
        sa.Column("position", sa.Integer(), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    for column in columns:
        op.add_column("books", column)

    checks = (
        ("ck_books_isbn_10_length", "isbn_10 IS NULL OR length(isbn_10) = 10"),
        ("ck_books_isbn_13_length", "isbn_13 IS NULL OR length(isbn_13) = 13"),
        ("ck_books_page_count", "page_count IS NULL OR page_count > 0"),
        (
            "ck_books_current_ed_year",
            "current_ed_year IS NULL OR current_ed_year BETWEEN 1000 AND 9999",
        ),
        (
            "ck_books_original_publication_year",
            "original_publication_year IS NULL OR "
            "original_publication_year BETWEEN 1000 AND 9999",
        ),
        (
            "ck_books_translation_status",
            "translation_status IN ('UNKNOWN', 'ORIGINAL', 'TRANSLATED')",
        ),
        (
            "ck_books_edition_number",
            "edition_number IS NULL OR edition_number > 0",
        ),
        (
            "ck_books_fiction_category",
            "fiction_category IS NULL OR "
            "fiction_category IN ('FICTION', 'NON_FICTION')",
        ),
        (
            "ck_books_binding",
            "binding IS NULL OR binding IN "
            "('HARDCOVER', 'PAPERBACK', 'FLEXIBOUND', 'SPIRAL', "
            "'STAPLED', 'OTHER')",
        ),
        (
            "ck_books_publication_type",
            "publication_type IS NULL OR publication_type IN "
            "('CONVENTIONAL_BOOK', 'COMIC_GRAPHIC_NOVEL', 'ATLAS', "
            "'REFERENCE', 'ART_PHOTOGRAPHY_ILLUSTRATED', "
            "'MAGAZINE_PERIODICAL', 'OTHER')",
        ),
        ("ck_books_height_mm", "height_mm IS NULL OR height_mm > 0"),
        ("ck_books_width_mm", "width_mm IS NULL OR width_mm > 0"),
        (
            "ck_books_thickness_mm",
            "thickness_mm IS NULL OR thickness_mm > 0",
        ),
        (
            "ck_books_location_pair",
            "(container_id IS NULL AND position IS NULL) OR "
            "(container_id IS NOT NULL AND position IS NOT NULL)",
        ),
    )
    for name, expression in checks:
        op.create_check_constraint(name, "books", expression)

    op.create_unique_constraint("uq_books_library_id", "books", ["library_id", "id"])
    op.create_unique_constraint(
        "uq_books_container_position", "books", ["container_id", "position"]
    )
    op.create_foreign_key(
        "fk_books_library_container",
        "books",
        "containers",
        ["library_id", "container_id"],
        ["library_id", "id"],
        ondelete="RESTRICT",
    )
    op.create_index(
        "ix_books_library_author", "books", ["library_id", "author"]
    )
    op.create_index(
        "ix_books_library_isbn_10", "books", ["library_id", "isbn_10"]
    )
    op.create_index(
        "ix_books_library_isbn_13", "books", ["library_id", "isbn_13"]
    )


def _create_book_contributors() -> None:
    op.create_table(
        "book_contributors",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("role_code", sa.String(length=40), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=300), nullable=False),
        sa.Column(
            "normalized_name",
            sa.String(length=300),
            sa.Computed("lower(trim(name))", persisted=True),
        ),
        sa.CheckConstraint(
            "position > 0", name="ck_book_contributors_position"
        ),
        sa.CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 300",
            name="ck_book_contributors_name",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "book_id"],
            ["books.library_id", "books.id"],
            name="fk_book_contributors_library_book",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["role_code"], ["contributor_roles.code"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "book_id",
            "role_code",
            "position",
            name="uq_book_contributors_position",
        ),
        sa.UniqueConstraint(
            "book_id",
            "role_code",
            "normalized_name",
            name="uq_book_contributors_normalized_name",
        ),
    )
    op.create_index(
        "ix_book_contributors_library_book",
        "book_contributors",
        ["library_id", "book_id"],
    )
    op.create_index(
        "ix_book_contributors_role_name",
        "book_contributors",
        ["role_code", "name"],
    )


def _create_visual_layout() -> None:
    op.create_table(
        "visual_bookcase_layouts",
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("bookcase_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Numeric(14, 4), nullable=False),
        sa.Column("y", sa.Numeric(14, 4), nullable=False),
        sa.Column("width", sa.Numeric(14, 4), nullable=False),
        sa.Column("height", sa.Numeric(14, 4), nullable=False),
        sa.CheckConstraint("width > 0", name="ck_visual_bookcase_width"),
        sa.CheckConstraint("height > 0", name="ck_visual_bookcase_height"),
        sa.ForeignKeyConstraint(
            ["library_id", "bookcase_id"],
            ["bookcases.library_id", "bookcases.id"],
            name="fk_visual_bookcase_library_bookcase",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("library_id", "bookcase_id"),
    )
    op.create_table(
        "visual_shelf_layouts",
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("shelf_id", sa.Uuid(), nullable=False),
        sa.Column("height_weight", sa.Numeric(8, 4), nullable=False),
        sa.CheckConstraint(
            "height_weight > 0", name="ck_visual_shelf_weight"
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "shelf_id"],
            ["shelves.library_id", "shelves.id"],
            name="fk_visual_shelf_library_shelf",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("library_id", "shelf_id"),
    )
    op.create_table(
        "visual_container_layouts",
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("container_id", sa.Uuid(), nullable=False),
        sa.Column("x", sa.Numeric(7, 4), nullable=False),
        sa.Column("y", sa.Numeric(7, 4), nullable=False),
        sa.Column("width", sa.Numeric(7, 4), nullable=False),
        sa.Column("height", sa.Numeric(7, 4), nullable=False),
        sa.Column(
            "row_anchor",
            sa.String(length=8),
            server_default="LEFT",
            nullable=False,
        ),
        sa.Column("pile_support_kind", sa.String(length=8), nullable=True),
        sa.Column("pile_support_container_id", sa.Uuid(), nullable=True),
        sa.CheckConstraint(
            "x >= 0 AND x <= 100", name="ck_visual_container_x"
        ),
        sa.CheckConstraint(
            "y >= 0 AND y <= 100", name="ck_visual_container_y"
        ),
        sa.CheckConstraint(
            "width > 0 AND width <= 100 AND x + width <= 100",
            name="ck_visual_container_width",
        ),
        sa.CheckConstraint(
            "height > 0 AND height <= 100 AND y + height <= 100",
            name="ck_visual_container_height",
        ),
        sa.CheckConstraint(
            "row_anchor IN ('LEFT', 'RIGHT')",
            name="ck_visual_container_anchor",
        ),
        sa.CheckConstraint(
            "pile_support_kind IS NULL OR "
            "pile_support_kind IN ('SHELF', 'ROW')",
            name="ck_visual_container_support_kind",
        ),
        sa.CheckConstraint(
            "(pile_support_kind IS NULL AND pile_support_container_id IS NULL) OR "
            "(pile_support_kind = 'SHELF' AND "
            "pile_support_container_id IS NULL) OR "
            "(pile_support_kind = 'ROW' AND "
            "pile_support_container_id IS NOT NULL)",
            name="ck_visual_container_support_pair",
        ),
        sa.CheckConstraint(
            "pile_support_container_id IS NULL OR "
            "pile_support_container_id <> container_id",
            name="ck_visual_container_not_self_supported",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "container_id"],
            ["containers.library_id", "containers.id"],
            name="fk_visual_container_library_container",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "pile_support_container_id"],
            ["containers.library_id", "containers.id"],
            name="fk_visual_container_library_support",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("library_id", "container_id"),
    )
    op.create_table(
        "visual_outside_areas",
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("area_kind", sa.String(length=16), nullable=False),
        sa.Column("x", sa.Numeric(14, 4), nullable=False),
        sa.Column("y", sa.Numeric(14, 4), nullable=False),
        sa.Column("width", sa.Numeric(14, 4), nullable=False),
        sa.Column("height", sa.Numeric(14, 4), nullable=False),
        sa.CheckConstraint(
            "area_kind IN ('READING', 'LOANED')",
            name="ck_visual_outside_kind",
        ),
        sa.CheckConstraint("width > 0", name="ck_visual_outside_width"),
        sa.CheckConstraint("height > 0", name="ck_visual_outside_height"),
        sa.ForeignKeyConstraint(
            ["library_id"],
            ["libraries.id"],
            name="fk_visual_outside_library",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("library_id", "area_kind"),
    )


def upgrade() -> None:
    _create_contributor_roles()
    _create_physical_hierarchy()
    _expand_books()
    _create_book_contributors()
    _create_visual_layout()


def downgrade() -> None:
    op.drop_table("visual_outside_areas")
    op.drop_table("visual_container_layouts")
    op.drop_table("visual_shelf_layouts")
    op.drop_table("visual_bookcase_layouts")

    op.drop_index(
        "ix_book_contributors_role_name", table_name="book_contributors"
    )
    op.drop_index(
        "ix_book_contributors_library_book", table_name="book_contributors"
    )
    op.drop_table("book_contributors")

    op.drop_index("ix_books_library_isbn_13", table_name="books")
    op.drop_index("ix_books_library_isbn_10", table_name="books")
    op.drop_index("ix_books_library_author", table_name="books")
    op.drop_constraint("fk_books_library_container", "books", type_="foreignkey")
    op.drop_constraint("uq_books_container_position", "books", type_="unique")
    op.drop_constraint("uq_books_library_id", "books", type_="unique")
    for constraint in (
        "ck_books_location_pair",
        "ck_books_thickness_mm",
        "ck_books_width_mm",
        "ck_books_height_mm",
        "ck_books_publication_type",
        "ck_books_binding",
        "ck_books_fiction_category",
        "ck_books_edition_number",
        "ck_books_translation_status",
        "ck_books_original_publication_year",
        "ck_books_current_ed_year",
        "ck_books_page_count",
        "ck_books_isbn_13_length",
        "ck_books_isbn_10_length",
    ):
        op.drop_constraint(constraint, "books", type_="check")
    for column in (
        "updated_at",
        "position",
        "container_id",
        "thickness_mm",
        "width_mm",
        "height_mm",
        "is_original_collection",
        "acquisition_date",
        "notes",
        "goodreads_url",
        "series_volume",
        "series_name",
        "genre_text",
        "publication_type",
        "binding",
        "fiction_category",
        "edition_number",
        "translation_status",
        "original_language",
        "language",
        "original_publication_year",
        "current_ed_year",
        "publisher",
        "page_count",
        "subtitle",
        "isbn_13",
        "isbn_10",
    ):
        op.drop_column("books", column)

    op.drop_index("ix_containers_library_shelf", table_name="containers")
    op.drop_table("containers")
    op.drop_index("ix_shelves_library_bookcase", table_name="shelves")
    op.drop_table("shelves")
    op.drop_index("ix_bookcases_library_id", table_name="bookcases")
    op.drop_table("bookcases")
    op.drop_table("contributor_roles")
