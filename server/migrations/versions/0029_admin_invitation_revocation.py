"""Allow the runtime to revoke one account invitation with immutable audit."""

from alembic import op


revision = "0029_admin_invitation_revocation"
down_revision = "0028_admin_webauthn_step_up"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE SCHEMA platform_actions AUTHORIZATION bookpile_admin_audit_owner;
        GRANT SELECT (id, consumed_at, revoked_at, expires_at), UPDATE (revoked_at)
            ON public.account_invitations TO bookpile_admin_audit_owner;

        CREATE FUNCTION platform_actions.revoke_account_invitation(
            p_operator uuid, p_invitation uuid, p_authorized_until timestamptz
        ) RETURNS text
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_consumed_at timestamptz;
            v_revoked_at timestamptz;
            v_expires_at timestamptz;
            v_now timestamptz;
        BEGIN
            SELECT consumed_at, revoked_at, expires_at
              INTO v_consumed_at, v_revoked_at, v_expires_at
              FROM public.account_invitations
             WHERE id = p_invitation
               FOR UPDATE;

            v_now := clock_timestamp();
            IF p_authorized_until IS NULL OR v_now >= p_authorized_until THEN
                RETURN 'expired';
            END IF;
            IF NOT FOUND OR v_consumed_at IS NOT NULL THEN
                RETURN 'unavailable';
            END IF;
            IF v_revoked_at IS NOT NULL THEN
                RETURN 'revoked';
            END IF;
            IF v_now >= v_expires_at THEN
                RETURN 'unavailable';
            END IF;

            UPDATE public.account_invitations SET revoked_at = v_now WHERE id = p_invitation;
            PERFORM admin_audit.append_entry(
                p_operator::text, 'account_invitation.revoke', p_invitation::text,
                'console-revocation', gen_random_uuid()::text, 'succeeded'
            );
            RETURN 'revoked';
        END
        $function$;

        ALTER FUNCTION platform_actions.revoke_account_invitation(uuid, uuid, timestamptz)
            OWNER TO bookpile_admin_audit_owner;
        REVOKE ALL ON SCHEMA platform_actions FROM PUBLIC;
        REVOKE ALL ON FUNCTION platform_actions.revoke_account_invitation(uuid, uuid, timestamptz) FROM PUBLIC;
        GRANT USAGE ON SCHEMA platform_actions TO bookpile_runtime;
        GRANT EXECUTE ON FUNCTION platform_actions.revoke_account_invitation(uuid, uuid, timestamptz)
            TO bookpile_runtime;
    """)


def downgrade() -> None:
    op.execute("""
        DROP FUNCTION platform_actions.revoke_account_invitation(uuid, uuid, timestamptz);
        DROP SCHEMA platform_actions;
        REVOKE SELECT (id, consumed_at, revoked_at, expires_at), UPDATE (revoked_at)
            ON public.account_invitations FROM bookpile_admin_audit_owner;
    """)
