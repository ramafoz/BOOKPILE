"""Track active days and earned beta invitations.

Revision ID: 0018_beta_invitation_progress
Revises: 0017_account_recovery_token
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0018_beta_invitation_progress"
down_revision: str | None = "0017_account_recovery_token"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "beta_invitation_progress",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("active_day_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("available_credits", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_active_on", sa.Date(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "active_day_count BETWEEN 0 AND 2",
            name="ck_beta_invitation_progress_active_days",
        ),
        sa.CheckConstraint(
            "available_credits >= 0",
            name="ck_beta_invitation_progress_credits",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        "INSERT INTO beta_invitation_progress "
        "(user_id, active_day_count, available_credits) "
        "SELECT id, 0, 0 FROM users"
    )


def downgrade() -> None:
    op.drop_table("beta_invitation_progress")
