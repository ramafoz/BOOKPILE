"""Store short-lived WebAuthn reverification for platform sessions."""

from alembic import op
import sqlalchemy as sa


revision = "0028_admin_webauthn_step_up"
down_revision = "0027_platform_admin_access"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("platform_admin_access", sa.Column("step_up_session_hash", sa.String(64)))
    op.add_column("platform_admin_access", sa.Column("step_up_challenge", sa.LargeBinary()))
    op.add_column("platform_admin_access", sa.Column("step_up_challenge_expires_at", sa.DateTime(timezone=True)))
    op.add_column("platform_admin_access", sa.Column("step_up_verified_at", sa.DateTime(timezone=True)))
    op.execute("""
        GRANT UPDATE (step_up_session_hash, step_up_challenge,
                      step_up_challenge_expires_at, step_up_verified_at)
            ON public.platform_admin_access TO bookpile_runtime
    """)


def downgrade() -> None:
    for column in ("step_up_verified_at", "step_up_challenge_expires_at", "step_up_challenge", "step_up_session_hash"):
        op.drop_column("platform_admin_access", column)
