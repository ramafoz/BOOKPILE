"""Create the minimal library-scoped catalogue foundation.

Revision ID: 0001_server_foundation
Revises: None
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0001_server_foundation"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "libraries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_table(
        "books",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=500), nullable=False),
        sa.Column("author", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_id"], ["libraries.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_books_library_id", "books", ["library_id"])
    op.create_index(
        "ix_books_library_title", "books", ["library_id", "title"]
    )


def downgrade() -> None:
    op.drop_index("ix_books_library_title", table_name="books")
    op.drop_index("ix_books_library_id", table_name="books")
    op.drop_table("books")
    op.drop_table("libraries")

