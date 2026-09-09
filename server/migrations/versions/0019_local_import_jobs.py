"""Add short-lived Local ZIP preflight jobs.

Revision ID: 0019_local_import_jobs
Revises: 0018_beta_invitation_progress
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0019_local_import_jobs"
down_revision: str | None = "0018_beta_invitation_progress"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "library_import_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("reading_owner_user_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(16), server_default="READY", nullable=False),
        sa.Column("adapter", sa.String(40), nullable=False),
        sa.Column("backup_format_version", sa.Integer(), nullable=False),
        sa.Column("local_schema_version", sa.Integer(), nullable=False),
        sa.Column("source_created_at", sa.String(64), nullable=False),
        sa.Column("archive_sha256", sa.String(64), nullable=False),
        sa.Column("source_fingerprint", sa.String(64), nullable=False),
        sa.Column("staging_sha256", sa.String(64), nullable=False),
        sa.Column("staging_key", sa.String(64), nullable=False),
        sa.Column("source_counts", sa.JSON(), nullable=False),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("archive_bytes", sa.BigInteger(), nullable=False),
        sa.Column("uncompressed_bytes", sa.BigInteger(), nullable=False),
        sa.Column("estimated_logical_bytes", sa.BigInteger(), nullable=False),
        sa.Column("capacity_available", sa.Boolean(), nullable=False),
        sa.Column("result_counts", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('READY', 'IMPORTING', 'IMPORTED', 'FAILED', 'EXPIRED')",
            name="ck_library_import_jobs_state",
        ),
        sa.CheckConstraint("archive_bytes >= 0", name="ck_library_import_jobs_archive_bytes"),
        sa.CheckConstraint("uncompressed_bytes >= 0", name="ck_library_import_jobs_expanded_bytes"),
        sa.CheckConstraint("estimated_logical_bytes >= 0", name="ck_library_import_jobs_estimate"),
        sa.ForeignKeyConstraint(["library_id"], ["libraries.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reading_owner_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("staging_key"),
    )
    op.create_index(
        "ix_library_import_jobs_fingerprint",
        "library_import_jobs",
        ["library_id", "archive_sha256", "state"],
    )
    op.create_index(
        "ix_library_import_jobs_expiry",
        "library_import_jobs",
        ["state", "expires_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_library_import_jobs_expiry", table_name="library_import_jobs")
    op.drop_index("ix_library_import_jobs_fingerprint", table_name="library_import_jobs")
    op.drop_table("library_import_jobs")
