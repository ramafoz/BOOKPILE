"""Persist each account's preferred interface language.

Revision ID: 0023_account_locale
Revises: 0022_email_delivery_receipts
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0023_account_locale"
down_revision: str | None = "0022_email_delivery_receipts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("preferred_locale", sa.String(16), nullable=False, server_default="en"),
    )


def downgrade() -> None:
    op.drop_column("users", "preferred_locale")
