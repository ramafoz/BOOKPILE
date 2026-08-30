"""Add hashed email-verification and password-reset tokens.

Revision ID: 0004_account_action_tokens
Revises: 0003_account_invitations
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0004_account_action_tokens"
down_revision: str | None = "0003_account_invitations"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "account_action_tokens",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "purpose IN ('email_verification', 'password_reset')",
            name="ck_account_action_tokens_purpose",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index(
        "ix_account_action_tokens_expires_at",
        "account_action_tokens",
        ["expires_at"],
    )
    op.create_index(
        "ix_account_action_tokens_user_purpose",
        "account_action_tokens",
        ["user_id", "purpose"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_account_action_tokens_user_purpose",
        table_name="account_action_tokens",
    )
    op.drop_index(
        "ix_account_action_tokens_expires_at",
        table_name="account_action_tokens",
    )
    op.drop_table("account_action_tokens")
