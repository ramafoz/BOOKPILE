"""Add secure account recovery tokens.

Revision ID: 0017_account_recovery_token
Revises: 0016_account_deletion
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0017_account_recovery_token"
down_revision: str | None = "0016_account_deletion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "account_deletion_tombstones",
        sa.Column("recovery_token_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "account_deletion_tombstones",
        sa.Column("recovery_token_consumed_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_unique_constraint(
        "uq_account_deletion_tombstones_recovery_token",
        "account_deletion_tombstones",
        ["recovery_token_hash"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "uq_account_deletion_tombstones_recovery_token",
        "account_deletion_tombstones",
        type_="unique",
    )
    op.drop_column("account_deletion_tombstones", "recovery_token_consumed_at")
    op.drop_column("account_deletion_tombstones", "recovery_token_hash")
