"""Create account invitations with immutable audit in one transaction."""

from alembic import op


revision = "0030_admin_invitation_creation"
down_revision = "0029_admin_invitation_revocation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        GRANT INSERT (id, token_hash, created_by_user_id, created_at, expires_at)
            ON public.account_invitations TO bookpile_admin_audit_owner;

        CREATE FUNCTION platform_actions.create_account_invitation(
            p_operator uuid, p_invitation uuid, p_token_hash text,
            p_created_at timestamptz, p_expires_at timestamptz, p_authorized_until timestamptz
        ) RETURNS text
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        BEGIN
            IF p_authorized_until IS NULL OR clock_timestamp() >= p_authorized_until THEN
                RETURN 'expired';
            END IF;
            INSERT INTO public.account_invitations (id, token_hash, created_by_user_id, created_at, expires_at)
            VALUES (p_invitation, p_token_hash, p_operator, p_created_at, p_expires_at);
            PERFORM admin_audit.append_entry(
                p_operator::text, 'account_invitation.create', p_invitation::text,
                'console-creation', gen_random_uuid()::text, 'succeeded'
            );
            RETURN 'created';
        END
        $function$;

        ALTER FUNCTION platform_actions.create_account_invitation(uuid, uuid, text, timestamptz, timestamptz, timestamptz)
            OWNER TO bookpile_admin_audit_owner;
        REVOKE ALL ON FUNCTION platform_actions.create_account_invitation(uuid, uuid, text, timestamptz, timestamptz, timestamptz)
            FROM PUBLIC;
        GRANT EXECUTE ON FUNCTION platform_actions.create_account_invitation(uuid, uuid, text, timestamptz, timestamptz, timestamptz)
            TO bookpile_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION platform_actions.create_account_invitation(uuid, uuid, text, timestamptz, timestamptz, timestamptz);
        REVOKE INSERT (id, token_hash, created_by_user_id, created_at, expires_at)
            ON public.account_invitations FROM bookpile_admin_audit_owner;
    """)
