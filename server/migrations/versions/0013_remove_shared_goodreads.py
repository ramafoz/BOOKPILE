"""Remove the obsolete shared Goodreads review field from books.

Revision ID: 0013_remove_shared_goodreads
Revises: 0012_personal_readings

Phase 5 stores Goodreads review links exclusively in personal_book_records.
The upgrade deliberately refuses to discard any nonblank legacy value so an
unexpected installation must be audited and migrated explicitly first.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0013_remove_shared_goodreads"
down_revision: str | None = "0012_personal_readings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    connection = op.get_bind()
    legacy_count = connection.scalar(
        sa.text(
            "SELECT count(*) FROM books "
            "WHERE goodreads_url IS NOT NULL AND length(trim(goodreads_url)) > 0"
        )
    )
    if legacy_count:
        raise RuntimeError(
            "Cannot remove books.goodreads_url: "
            f"{legacy_count} nonblank legacy value(s) require manual migration"
        )
    op.drop_column("books", "goodreads_url")


def downgrade() -> None:
    op.add_column(
        "books",
        sa.Column("goodreads_url", sa.String(length=2048), nullable=True),
    )
