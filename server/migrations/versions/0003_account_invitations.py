"""Separate temporary account invitations from future library invitations.

Revision ID: 0003_account_invitations
Revises: 0002_identity_foundation
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0003_account_invitations"
down_revision: str | None = "0002_identity_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("ck_users_state", "users", type_="check")
    op.execute(
        "UPDATE users SET state = 'pending_verification' WHERE state = 'invited'"
    )
    op.create_check_constraint(
        "ck_users_state",
        "users",
        "state IN ('pending_verification', 'active', 'suspended', "
        "'pending_deletion', 'deleted')",
    )
    op.alter_column(
        "users",
        "state",
        server_default="pending_verification",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.create_table(
        "account_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("consumed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("consumed_by_user_id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_account_invitations_expires_at",
        "account_invitations",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_invitations_expires_at", table_name="account_invitations"
    )
    op.drop_table("account_invitations")
    op.alter_column(
        "users",
        "state",
        server_default="invited",
        existing_type=sa.String(length=32),
        existing_nullable=False,
    )
    op.drop_constraint("ck_users_state", "users", type_="check")
    op.execute(
        "UPDATE users SET state = 'invited' WHERE state = 'pending_verification'"
    )
    op.create_check_constraint(
        "ck_users_state",
        "users",
        "state IN ('invited', 'active', 'suspended', "
        "'pending_deletion', 'deleted')",
    )
