"""Add recoverable account deletion tombstones.

Revision ID: 0016_account_deletion
Revises: 0015_profiles_storage
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0016_account_deletion"
down_revision: str | None = "0015_profiles_storage"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_deletion_tombstones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("username", sa.String(30), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("state", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("membership_snapshot", sa.JSON(), nullable=False),
        sa.Column("object_manifest", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recover_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('PENDING', 'RECOVERED', 'FINALIZED')",
            name="ck_account_deletion_tombstones_state",
        ),
        sa.CheckConstraint(
            "recover_until > created_at",
            name="ck_account_deletion_tombstones_window",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_account_deletion_tombstones_recovery",
        "account_deletion_tombstones",
        ["state", "recover_until"],
    )
    op.create_index(
        "uq_account_deletion_tombstones_pending",
        "account_deletion_tombstones",
        ["user_id"],
        unique=True,
        postgresql_where=sa.text("state = 'PENDING'"),
    )


def downgrade() -> None:
    count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM account_deletion_tombstones")
    )
    if count:
        raise RuntimeError("Cannot remove account deletion schema while tombstones exist")
    op.drop_index(
        "uq_account_deletion_tombstones_pending",
        table_name="account_deletion_tombstones",
    )
    op.drop_index(
        "ix_account_deletion_tombstones_recovery",
        table_name="account_deletion_tombstones",
    )
    op.drop_table("account_deletion_tombstones")
