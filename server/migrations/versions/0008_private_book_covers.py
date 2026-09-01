"""Add private, library-scoped book-cover metadata.

Revision ID: 0008_private_book_covers
Revises: 0007_shared_catalogue_schema
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0008_private_book_covers"
down_revision: str | None = "0007_shared_catalogue_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "book_covers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(length=160), nullable=False),
        sa.Column("media_type", sa.String(length=32), server_default="image/webp", nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("media_type = 'image/webp'", name="ck_book_covers_media_type"),
        sa.CheckConstraint("byte_size > 0", name="ck_book_covers_byte_size"),
        sa.CheckConstraint("width_px > 0", name="ck_book_covers_width_px"),
        sa.CheckConstraint("height_px > 0", name="ck_book_covers_height_px"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_book_covers_sha256"),
        sa.ForeignKeyConstraint(
            ["library_id", "book_id"], ["books.library_id", "books.id"],
            name="fk_book_covers_library_book", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("book_id", name="uq_book_covers_book_id"),
        sa.UniqueConstraint("object_key", name="uq_book_covers_object_key"),
    )
    op.create_index("ix_book_covers_library_id", "book_covers", ["library_id"])


def downgrade() -> None:
    op.drop_index("ix_book_covers_library_id", table_name="book_covers")
    op.drop_table("book_covers")
