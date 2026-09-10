"""Add Server restore metadata to import jobs.

Revision ID: 0020_server_restore_jobs
Revises: 0019_local_import_jobs
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0020_server_restore_jobs"
down_revision: str | None = "0019_local_import_jobs"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "library_import_jobs",
        sa.Column("source_kind", sa.String(length=16), nullable=False, server_default="LOCAL"),
    )
    op.add_column(
        "library_import_jobs",
        sa.Column("source_members", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.add_column(
        "library_import_jobs",
        sa.Column("source_library_name", sa.String(length=160), nullable=True),
    )
    op.alter_column("library_import_jobs", "source_kind", server_default=None)
    op.alter_column("library_import_jobs", "source_members", server_default=None)
    op.create_check_constraint(
        "ck_library_import_jobs_source_kind",
        "library_import_jobs",
        "source_kind IN ('LOCAL', 'SERVER')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_library_import_jobs_source_kind",
        "library_import_jobs",
        type_="check",
    )
    op.drop_column("library_import_jobs", "source_library_name")
    op.drop_column("library_import_jobs", "source_members")
    op.drop_column("library_import_jobs", "source_kind")
