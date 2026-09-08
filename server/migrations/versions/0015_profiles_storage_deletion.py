"""Add private profiles, logical storage allocation and deletion tombstones.

Revision ID: 0015_profiles_storage
Revises: 0014_shared_loans

All structures are additive. Existing accounts receive the free-beta entitlement;
usage and allocation rows are deliberately populated only by the audited 7B
backfill service, never guessed by the migration.
"""
from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "0015_profiles_storage"
down_revision: str | None = "0014_shared_loans"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_profiles",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(100), nullable=True),
        sa.Column("timezone", sa.String(64), nullable=True),
        sa.Column("gender", sa.String(16), server_default="UNSPECIFIED", nullable=False),
        sa.Column("custom_gender", sa.String(80), nullable=True),
        sa.Column("preferred_pronoun", sa.String(16), nullable=True),
        sa.Column("neutral_pronoun", sa.String(80), nullable=True),
        sa.Column("city", sa.String(120), nullable=True),
        sa.Column("state", sa.String(120), nullable=True),
        sa.Column("country", sa.String(120), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "gender IN ('UNSPECIFIED', 'MALE', 'FEMALE', 'CUSTOM')",
            name="ck_user_profiles_gender",
        ),
        sa.CheckConstraint(
            "preferred_pronoun IS NULL OR preferred_pronoun IN ('MALE', 'FEMALE', 'NEUTRAL')",
            name="ck_user_profiles_pronoun",
        ),
        sa.CheckConstraint(
            "(gender <> 'CUSTOM' AND custom_gender IS NULL AND preferred_pronoun IS NULL "
            "AND neutral_pronoun IS NULL) OR (gender = 'CUSTOM' AND custom_gender IS NOT NULL "
            "AND length(trim(custom_gender)) > 0 AND preferred_pronoun IS NOT NULL "
            "AND (preferred_pronoun = 'NEUTRAL' OR neutral_pronoun IS NULL))",
            name="ck_user_profiles_gender_shape",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_table(
        "user_profile_field_visibilities",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("field_name", sa.String(32), nullable=False),
        sa.Column("visibility", sa.String(32), server_default="PRIVATE", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint(
            "field_name IN ('display_name', 'timezone', 'gender', 'city', 'state', "
            "'country', 'date_of_birth', 'profile_image')",
            name="ck_profile_visibilities_field",
        ),
        sa.CheckConstraint(
            "visibility IN ('PRIVATE', 'SHARED_LIBRARY_MEMBERS', 'AUTHENTICATED')",
            name="ck_profile_visibilities_value",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "field_name"),
    )
    op.create_table(
        "user_profile_images",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("object_key", sa.String(160), nullable=False),
        sa.Column("media_type", sa.String(32), server_default="image/webp", nullable=False),
        sa.Column("byte_size", sa.BigInteger(), nullable=False),
        sa.Column("width_px", sa.Integer(), nullable=False),
        sa.Column("height_px", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("media_type = 'image/webp'", name="ck_profile_images_media_type"),
        sa.CheckConstraint("byte_size > 0", name="ck_profile_images_byte_size"),
        sa.CheckConstraint("width_px > 0", name="ck_profile_images_width_px"),
        sa.CheckConstraint("height_px > 0", name="ck_profile_images_height_px"),
        sa.CheckConstraint("length(sha256) = 64", name="ck_profile_images_sha256"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
        sa.UniqueConstraint("object_key"),
    )
    op.create_table(
        "account_storage_entitlements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("plan_code", sa.String(40), server_default="FREE_BETA", nullable=False),
        sa.Column("limit_bytes", sa.BigInteger(), server_default="100000000", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("limit_bytes > 0", name="ck_storage_entitlements_limit"),
        sa.CheckConstraint("length(trim(plan_code)) > 0", name="ck_storage_entitlements_plan"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.execute(
        sa.text(
            "INSERT INTO account_storage_entitlements (user_id, plan_code, limit_bytes) "
            "SELECT id, 'FREE_BETA', 100000000 FROM users"
        )
    )
    op.create_table(
        "library_storage_usages",
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("logical_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("accounting_version", sa.Integer(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("calculated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("logical_size_bytes >= 0", name="ck_library_storage_usage_size"),
        sa.CheckConstraint("accounting_version > 0", name="ck_library_storage_usage_version"),
        sa.CheckConstraint("revision >= 0", name="ck_library_storage_usage_revision"),
        sa.ForeignKeyConstraint(["library_id"], ["libraries.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("library_id"),
    )
    op.create_table(
        "library_storage_allocations",
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("allocated_bytes", sa.BigInteger(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("allocated_bytes >= 0", name="ck_library_storage_allocation_size"),
        sa.ForeignKeyConstraint(
            ["library_id", "user_id"],
            ["library_memberships.library_id", "library_memberships.user_id"],
            name="fk_storage_allocations_membership",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("library_id", "user_id"),
    )
    op.create_index("ix_storage_allocations_user", "library_storage_allocations", ["user_id"])
    op.create_table(
        "library_deletion_tombstones",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("library_id", sa.Uuid(), nullable=False),
        sa.Column("library_name", sa.String(160), nullable=False),
        sa.Column("requested_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("state", sa.String(16), server_default="PENDING", nullable=False),
        sa.Column("logical_size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("membership_snapshot", sa.JSON(), nullable=False),
        sa.Column("allocation_snapshot", sa.JSON(), nullable=False),
        sa.Column("object_manifest", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("recover_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("recovered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "state IN ('PENDING', 'RECOVERED', 'FINALIZED')",
            name="ck_library_deletion_tombstones_state",
        ),
        sa.CheckConstraint("logical_size_bytes >= 0", name="ck_library_deletion_tombstones_size"),
        sa.CheckConstraint("recover_until > created_at", name="ck_library_deletion_tombstones_window"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_library_deletion_tombstones_recovery",
        "library_deletion_tombstones",
        ["state", "recover_until"],
    )
    op.create_index(
        "uq_library_deletion_tombstones_pending",
        "library_deletion_tombstones",
        ["library_id"],
        unique=True,
        postgresql_where=sa.text("state = 'PENDING'"),
    )


def downgrade() -> None:
    tombstone_count = op.get_bind().scalar(
        sa.text("SELECT count(*) FROM library_deletion_tombstones")
    )
    if tombstone_count:
        raise RuntimeError("Cannot remove storage schema while deletion tombstones exist")
    op.drop_index("uq_library_deletion_tombstones_pending", table_name="library_deletion_tombstones")
    op.drop_index("ix_library_deletion_tombstones_recovery", table_name="library_deletion_tombstones")
    op.drop_table("library_deletion_tombstones")
    op.drop_index("ix_storage_allocations_user", table_name="library_storage_allocations")
    op.drop_table("library_storage_allocations")
    op.drop_table("library_storage_usages")
    op.drop_table("account_storage_entitlements")
    op.drop_table("user_profile_images")
    op.drop_table("user_profile_field_visibilities")
    op.drop_table("user_profiles")
