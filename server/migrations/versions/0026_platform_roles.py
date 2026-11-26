"""Add explicit platform role assignments.

Revision ID: 0026_platform_roles
Revises: 0025_immutable_admin_audit
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0026_platform_roles"
down_revision: str | None = "0025_immutable_admin_audit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "platform_roles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.CheckConstraint("role = 'SYSTEM_ADMIN'", name="ck_platform_roles_role"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role"),
    )
    op.execute("REVOKE ALL ON public.platform_roles FROM PUBLIC, bookpile_runtime")
    op.execute("GRANT SELECT ON public.platform_roles TO bookpile_runtime")
    op.execute("""
        DO $backup$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bookpile_backup') THEN
                GRANT SELECT ON public.platform_roles TO bookpile_backup;
            END IF;
        END
        $backup$;
    """)


def downgrade() -> None:
    op.execute("LOCK TABLE public.platform_roles IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $downgrade$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.platform_roles) THEN
                RAISE EXCEPTION 'Cannot downgrade with existing platform role assignments';
            END IF;
        END
        $downgrade$;
    """)
    op.drop_table("platform_roles")
