"""Add shared fixed-window authentication rate-limit buckets.

Revision ID: 0005_rate_limit_buckets
Revises: 0004_account_action_tokens
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0005_rate_limit_buckets"
down_revision: str | None = "0004_account_action_tokens"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "rate_limit_buckets",
        sa.Column("scope", sa.String(length=64), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "attempt_count > 0", name="ck_rate_limit_buckets_attempt_count"
        ),
        sa.PrimaryKeyConstraint("scope", "key_hash"),
    )
    op.create_index(
        "ix_rate_limit_buckets_updated_at",
        "rate_limit_buckets",
        ["updated_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_rate_limit_buckets_updated_at", table_name="rate_limit_buckets"
    )
    op.drop_table("rate_limit_buckets")
