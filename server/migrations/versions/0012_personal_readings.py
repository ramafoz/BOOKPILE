"""Add Owner-scoped reading sessions and personal book records.

Revision ID: 0012_personal_readings
Revises: 0011_explicit_shelves

This migration is additive. The dormant books.goodreads_url compatibility
column is intentionally retained until Phase 5E performs an explicit audit.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0012_personal_readings"
down_revision: str | None = "0011_explicit_shelves"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reading_sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("started_date", sa.Date(), nullable=True),
        sa.Column("finished_date", sa.Date(), nullable=True),
        sa.Column(
            "dates_unknown",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state IN ('ACTIVE', 'COMPLETED')",
            name="ck_reading_sessions_state",
        ),
        sa.CheckConstraint(
            "(state = 'ACTIVE' AND dates_unknown = false "
            "AND started_date IS NOT NULL AND finished_date IS NULL) OR "
            "(state = 'COMPLETED' AND dates_unknown = false "
            "AND started_date IS NOT NULL AND finished_date IS NOT NULL "
            "AND finished_date >= started_date) OR "
            "(state = 'COMPLETED' AND dates_unknown = true "
            "AND started_date IS NULL AND finished_date IS NULL)",
            name="ck_reading_sessions_date_shape",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "book_id"],
            ["books.library_id", "books.id"],
            name="fk_reading_sessions_library_book",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_reading_sessions_active_book",
        "reading_sessions",
        ["book_id"],
        unique=True,
        postgresql_where=sa.text("state = 'ACTIVE'"),
    )
    op.create_index(
        "uq_reading_sessions_unknown_owner_book",
        "reading_sessions",
        ["library_id", "book_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("dates_unknown = true"),
    )
    op.create_index(
        "ix_reading_sessions_owner_book_dates",
        "reading_sessions",
        ["library_id", "user_id", "book_id", "started_date", "finished_date"],
        unique=False,
    )

    op.create_table(
        "personal_book_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("goodreads_url", sa.String(2048), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "goodreads_url IS NULL OR length(trim(goodreads_url)) > 0",
            name="ck_personal_book_records_goodreads_nonblank",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "book_id"],
            ["books.library_id", "books.id"],
            name="fk_personal_book_records_library_book",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "library_id",
            "book_id",
            "user_id",
            name="uq_personal_book_records_owner_book",
        ),
    )
    op.create_index(
        "ix_personal_book_records_owner",
        "personal_book_records",
        ["library_id", "user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_personal_book_records_owner", table_name="personal_book_records"
    )
    op.drop_table("personal_book_records")
    op.drop_index(
        "ix_reading_sessions_owner_book_dates", table_name="reading_sessions"
    )
    op.drop_index(
        "uq_reading_sessions_unknown_owner_book", table_name="reading_sessions"
    )
    op.drop_index(
        "uq_reading_sessions_active_book", table_name="reading_sessions"
    )
    op.drop_table("reading_sessions")
