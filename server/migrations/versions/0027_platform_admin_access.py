"""Store host-approved first credentials and separate platform sessions."""

from alembic import op
import sqlalchemy as sa


revision = "0027_platform_admin_access"
down_revision = "0026_platform_roles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "platform_admin_access",
        sa.Column("user_id", sa.Uuid(), primary_key=True),
        sa.Column("role", sa.String(16), server_default="SYSTEM_ADMIN", nullable=False),
        sa.Column("bootstrap_hash", sa.String(64), nullable=False),
        sa.Column("bootstrap_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("credential_id", sa.LargeBinary(), unique=True),
        sa.Column("public_key", sa.LargeBinary()),
        sa.Column("sign_count", sa.BigInteger()),
        sa.Column("challenge", sa.LargeBinary()),
        sa.Column("challenge_session_id", sa.Uuid()),
        sa.Column("challenge_expires_at", sa.DateTime(timezone=True)),
        sa.Column("session_hash", sa.String(64)),
        sa.Column("csrf_hash", sa.String(64)),
        sa.Column("parent_session_id", sa.Uuid()),
        sa.Column("last_active_at", sa.DateTime(timezone=True)),
        sa.Column("absolute_expires_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(
            ["user_id", "role"], ["platform_roles.user_id", "platform_roles.role"],
            ondelete="CASCADE",
        ),
    )
    op.execute("REVOKE ALL ON public.platform_admin_access FROM PUBLIC, bookpile_runtime")
    op.execute("""
        GRANT SELECT ON public.platform_admin_access TO bookpile_runtime;
        GRANT UPDATE (credential_id, public_key, sign_count, challenge,
                      challenge_session_id, challenge_expires_at, session_hash,
                      csrf_hash, parent_session_id, last_active_at, absolute_expires_at)
            ON public.platform_admin_access TO bookpile_runtime;
        DO $backup$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'bookpile_backup') THEN
                GRANT SELECT ON public.platform_admin_access TO bookpile_backup;
            END IF;
        END
        $backup$;
    """)


def downgrade() -> None:
    op.execute("LOCK TABLE public.platform_admin_access IN ACCESS EXCLUSIVE MODE")
    op.execute("""
        DO $downgrade$
        BEGIN
            IF EXISTS (SELECT 1 FROM public.platform_admin_access) THEN
                RAISE EXCEPTION 'Cannot downgrade with platform administrator access data';
            END IF;
        END
        $downgrade$;
    """)
    op.drop_table("platform_admin_access")
