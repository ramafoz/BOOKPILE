"""Add encrypted durable email outbox.

Revision ID: 0021_email_outbox
Revises: 0020_server_restore_jobs
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0021_email_outbox"
down_revision: str | None = "0020_server_restore_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "email_outbox_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_key", sa.String(128), nullable=False),
        sa.Column("purpose", sa.String(40), nullable=False),
        sa.Column("payload_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="PENDING"),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(80), nullable=True),
        sa.Column("account_action_token_id", sa.Uuid(), nullable=True),
        sa.Column("account_deletion_tombstone_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("purpose IN ('EMAIL_VERIFICATION', 'PASSWORD_RESET', 'ACCOUNT_DELETION_RECOVERY')", name="ck_email_outbox_purpose"),
        sa.CheckConstraint("state IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED', 'CANCELLED')", name="ck_email_outbox_state"),
        sa.CheckConstraint("attempt_count >= 0", name="ck_email_outbox_attempts"),
        sa.ForeignKeyConstraint(["account_action_token_id"], ["account_action_tokens.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["account_deletion_tombstone_id"], ["account_deletion_tombstones.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_key", name="uq_email_outbox_message_key"),
    )
    op.create_index(
        "ix_email_outbox_delivery",
        "email_outbox_messages",
        ["state", "available_at"],
    )


def downgrade() -> None:
    pending = op.get_bind().execute(
        sa.text("SELECT count(*) FROM email_outbox_messages")
    ).scalar_one()
    if pending:
        raise RuntimeError(
            "Refusing to remove a non-empty email outbox; deliver or explicitly "
            "resolve its messages first."
        )
    op.drop_index("ix_email_outbox_delivery", table_name="email_outbox_messages")
    op.drop_table("email_outbox_messages")
