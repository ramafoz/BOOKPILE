"""Add shared operation leases with monotonic fencing tokens.

Revision ID: 0024_operation_leases
Revises: 0023_account_locale
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0024_operation_leases"
down_revision: str | None = "0023_account_locale"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "operation_leases",
        sa.Column("scope", sa.String(64), nullable=False),
        sa.Column("key_hash", sa.String(64), nullable=False),
        sa.Column("lease_id", sa.Uuid(), nullable=False),
        sa.Column("fencing_token", sa.BigInteger(), nullable=False),
        sa.Column("acquired_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("renewed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "fencing_token > 0", name="ck_operation_leases_fencing_token"
        ),
        sa.PrimaryKeyConstraint("scope", "key_hash"),
        sa.UniqueConstraint("lease_id"),
    )
    op.create_index(
        "ix_operation_leases_expires_at", "operation_leases", ["expires_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_operation_leases_expires_at", table_name="operation_leases")
    op.drop_table("operation_leases")
