"""Add libraries, equal co-Owners, Viewer scopes, and invitations.

Revision ID: 0006_library_memberships
Revises: 0005_rate_limit_buckets
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0006_library_memberships"
down_revision: str | None = "0005_rate_limit_buckets"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _role_scope_constraints(prefix: str) -> list[sa.CheckConstraint]:
    return [
        sa.CheckConstraint(
            "role IN ('OWNER', 'VIEWER')", name=f"ck_{prefix}_role"
        ),
        sa.CheckConstraint(
            "viewer_scope IS NULL OR viewer_scope IN "
            "('CATALOG_ONLY', 'CATALOG_AND_MAP')",
            name=f"ck_{prefix}_viewer_scope_value",
        ),
        sa.CheckConstraint(
            "(role = 'OWNER' AND viewer_scope IS NULL) OR "
            "(role = 'VIEWER' AND viewer_scope IS NOT NULL)",
            name=f"ck_{prefix}_role_scope",
        ),
    ]


def upgrade() -> None:
    op.add_column(
        "libraries", sa.Column("created_by_user_id", sa.Uuid(), nullable=True)
    )
    op.add_column(
        "libraries",
        sa.Column(
            "state",
            sa.String(length=32),
            server_default="active",
            nullable=False,
        ),
    )
    op.add_column(
        "libraries",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_foreign_key(
        "fk_libraries_created_by_user_id_users",
        "libraries",
        "users",
        ["created_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_check_constraint(
        "ck_libraries_state",
        "libraries",
        "state IN ('active', 'pending_deletion', 'deleted')",
    )

    op.create_table(
        "library_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("viewer_scope", sa.String(length=32), nullable=True),
        sa.Column("selected_reading_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["library_id"], ["libraries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["selected_reading_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "library_id", "user_id", name="uq_library_memberships_library_user"
        ),
        *_role_scope_constraints("library_memberships"),
    )
    op.create_index(
        "ix_library_memberships_user_role",
        "library_memberships",
        ["user_id", "role"],
    )

    op.create_table(
        "library_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("viewer_scope", sa.String(length=32), nullable=True),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("consumed_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["library_id"], ["libraries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_hash"),
        *_role_scope_constraints("library_invitations"),
    )
    op.create_index(
        "ix_library_invitations_library_active",
        "library_invitations",
        ["library_id", "consumed_at"],
    )
    op.create_index(
        "ix_library_invitations_expires_at",
        "library_invitations",
        ["expires_at"],
    )

    op.create_table(
        "library_audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=80), nullable=False),
        sa.Column(
            "occurred_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("details", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(
            ["library_id"], ["libraries.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_library_audit_events_library_occurred",
        "library_audit_events",
        ["library_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_library_audit_events_library_occurred",
        table_name="library_audit_events",
    )
    op.drop_table("library_audit_events")
    op.drop_index(
        "ix_library_invitations_expires_at", table_name="library_invitations"
    )
    op.drop_index(
        "ix_library_invitations_library_active", table_name="library_invitations"
    )
    op.drop_table("library_invitations")
    op.drop_index(
        "ix_library_memberships_user_role", table_name="library_memberships"
    )
    op.drop_table("library_memberships")
    op.drop_constraint("ck_libraries_state", "libraries", type_="check")
    op.drop_constraint(
        "fk_libraries_created_by_user_id_users", "libraries", type_="foreignkey"
    )
    op.drop_column("libraries", "updated_at")
    op.drop_column("libraries", "state")
    op.drop_column("libraries", "created_by_user_id")
