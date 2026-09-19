"""Store privacy-safe SMTP acceptance receipts.

Revision ID: 0022_email_delivery_receipts
Revises: 0021_email_outbox
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0022_email_delivery_receipts"
down_revision: str | None = "0021_email_outbox"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "email_outbox_messages",
        sa.Column("smtp_response_code", sa.Integer(), nullable=True),
    )
    op.add_column(
        "email_outbox_messages",
        sa.Column("provider_queue_id", sa.String(64), nullable=True),
    )
    op.create_check_constraint(
        "ck_email_outbox_smtp_response_code",
        "email_outbox_messages",
        "smtp_response_code IS NULL OR smtp_response_code BETWEEN 200 AND 599",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_email_outbox_smtp_response_code",
        "email_outbox_messages",
        type_="check",
    )
    op.drop_column("email_outbox_messages", "provider_queue_id")
    op.drop_column("email_outbox_messages", "smtp_response_code")
