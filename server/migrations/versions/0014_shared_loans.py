"""Add shared physical-copy loan history.

Revision ID: 0014_shared_loans
Revises: 0013_remove_shared_goodreads
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0014_shared_loans"
down_revision: str | None = "0013_remove_shared_goodreads"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "loans",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("book_id", sa.Uuid(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("loaned_to", sa.String(300), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("loaned_date", sa.Date(), nullable=True),
        sa.Column("expected_return_date", sa.Date(), nullable=True),
        sa.Column("returned_date", sa.Date(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "state IN ('ACTIVE', 'RETURNED')", name="ck_loans_state"
        ),
        sa.CheckConstraint(
            "length(trim(loaned_to)) BETWEEN 1 AND 300",
            name="ck_loans_loaned_to",
        ),
        sa.CheckConstraint(
            "notes IS NULL OR length(notes) <= 4000",
            name="ck_loans_notes_length",
        ),
        sa.CheckConstraint(
            "state = 'RETURNED' OR returned_date IS NULL",
            name="ck_loans_active_has_no_returned_date",
        ),
        sa.CheckConstraint(
            "loaned_date IS NULL OR expected_return_date IS NULL OR "
            "expected_return_date >= loaned_date",
            name="ck_loans_expected_after_loaned",
        ),
        sa.CheckConstraint(
            "loaned_date IS NULL OR returned_date IS NULL OR "
            "returned_date >= loaned_date",
            name="ck_loans_returned_after_loaned",
        ),
        sa.ForeignKeyConstraint(
            ["library_id", "book_id"],
            ["books.library_id", "books.id"],
            name="fk_loans_library_book",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_loans_active_book", "loans", ["library_id", "book_id"],
        unique=True, postgresql_where=sa.text("state = 'ACTIVE'"),
    )
    op.create_index(
        "ix_loans_library_history", "loans",
        ["library_id", "state", "loaned_date", "returned_date", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    loan_count = op.get_bind().scalar(sa.text("SELECT count(*) FROM loans"))
    if loan_count:
        raise RuntimeError(
            "Cannot remove loans: loan history exists and must be preserved"
        )
    op.drop_index("ix_loans_library_history", table_name="loans")
    op.drop_index("uq_loans_active_book", table_name="loans")
    op.drop_table("loans")
