"""Add the insert-only, hash-chained SYSTEM_ADMIN audit ledger.

Revision ID: 0025_immutable_admin_audit
Revises: 0024_operation_leases
"""

from collections.abc import Sequence

from alembic import op
from sqlalchemy import text


revision: str = "0025_immutable_admin_audit"
down_revision: str | None = "0024_operation_leases"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_ROLES = (
    "bookpile_runtime",
    "bookpile_admin_audit_owner",
    "bookpile_admin_audit_writer",
    "bookpile_admin_audit_reader",
    "bookpile_admin_audit_backup",
    "bookpile_admin_audit_verifier",
    "bookpile_admin_audit_retention",
)


def upgrade() -> None:
    connection = op.get_bind()
    for role in _ROLES:
        connection.exec_driver_sql(
            f"DO $role$ BEGIN "
            f"IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{role}') THEN "
            f"CREATE ROLE {role} NOLOGIN NOSUPERUSER NOCREATEDB "
            f"NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; "
            f"END IF; END $role$"
        )
    unsafe_roles = connection.execute(
        text(
            "SELECT rolname FROM pg_roles WHERE rolname = ANY(:roles) AND "
            "(rolcanlogin OR rolsuper OR rolcreatedb OR rolcreaterole OR "
            "rolreplication OR rolbypassrls)"
        ),
        {"roles": list(_ROLES)},
    ).scalars().all()
    if unsafe_roles:
        raise RuntimeError(
            "pre-existing BOOKPILE group roles have unsafe attributes: "
            + ", ".join(sorted(unsafe_roles))
        )

    op.execute(
        """
        CREATE SCHEMA admin_audit AUTHORIZATION bookpile_admin_audit_owner;

        CREATE TABLE admin_audit.entries (
            sequence_id bigint PRIMARY KEY,
            event_id uuid NOT NULL UNIQUE,
            operator_id varchar(128) NOT NULL,
            action varchar(96) NOT NULL,
            target_id varchar(160),
            reason varchar(500) NOT NULL,
            correlation_id varchar(160) NOT NULL,
            occurred_at timestamptz NOT NULL,
            result varchar(16) NOT NULL,
            previous_hash char(64) NOT NULL,
            row_hash char(64) NOT NULL UNIQUE,
            CONSTRAINT ck_admin_audit_sequence_positive CHECK (sequence_id > 0),
            CONSTRAINT ck_admin_audit_operator CHECK (
                operator_id ~ '^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$'
            ),
            CONSTRAINT ck_admin_audit_action CHECK (
                action ~ '^[a-z][a-z0-9_.-]{2,95}$'
            ),
            CONSTRAINT ck_admin_audit_target CHECK (
                target_id IS NULL OR
                (length(target_id) BETWEEN 1 AND 160 AND
                 target_id !~ '[[:cntrl:]]')
            ),
            CONSTRAINT ck_admin_audit_reason CHECK (
                length(reason) BETWEEN 8 AND 500 AND
                reason !~ '[[:cntrl:]]'
            ),
            CONSTRAINT ck_admin_audit_correlation CHECK (
                length(correlation_id) BETWEEN 3 AND 160 AND
                correlation_id !~ '[[:cntrl:]]'
            ),
            CONSTRAINT ck_admin_audit_result CHECK (
                result IN ('attempted', 'succeeded', 'failed')
            ),
            CONSTRAINT ck_admin_audit_previous_hash CHECK (
                previous_hash ~ '^[0-9a-f]{64}$'
            ),
            CONSTRAINT ck_admin_audit_row_hash CHECK (
                row_hash ~ '^[0-9a-f]{64}$'
            )
        );
        ALTER TABLE admin_audit.entries OWNER TO bookpile_admin_audit_owner;

        CREATE TABLE admin_audit.chain_state (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            last_sequence_id bigint NOT NULL CHECK (last_sequence_id >= 0),
            last_hash char(64) NOT NULL CHECK (last_hash ~ '^[0-9a-f]{64}$')
        );
        ALTER TABLE admin_audit.chain_state OWNER TO bookpile_admin_audit_owner;
        INSERT INTO admin_audit.chain_state
            (singleton, last_sequence_id, last_hash)
        VALUES (true, 0, repeat('0', 64));

        CREATE TABLE admin_audit.retention_checkpoint (
            singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
            pruned_through_sequence_id bigint NOT NULL
                CHECK (pruned_through_sequence_id >= 0),
            pruned_through_hash char(64) NOT NULL
                CHECK (pruned_through_hash ~ '^[0-9a-f]{64}$'),
            pruned_at timestamptz
        );
        ALTER TABLE admin_audit.retention_checkpoint
            OWNER TO bookpile_admin_audit_owner;
        INSERT INTO admin_audit.retention_checkpoint
            (singleton, pruned_through_sequence_id, pruned_through_hash, pruned_at)
        VALUES (true, 0, repeat('0', 64), NULL);

        CREATE FUNCTION admin_audit.append_entry(
            p_operator_id text,
            p_action text,
            p_target_id text,
            p_reason text,
            p_correlation_id text,
            p_result text
        ) RETURNS TABLE (
            sequence_id bigint,
            event_id uuid,
            occurred_at timestamptz,
            row_hash text
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_previous_sequence bigint;
            v_previous_hash text;
            v_sequence bigint;
            v_event_id uuid := gen_random_uuid();
            v_occurred_at timestamptz := clock_timestamp();
            v_payload text;
            v_row_hash text;
        BEGIN
            IF p_operator_id IS NULL OR
               p_operator_id !~ '^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$' THEN
                RAISE EXCEPTION 'invalid admin audit operator';
            END IF;
            IF p_action IS NULL OR
               p_action !~ '^[a-z][a-z0-9_.-]{2,95}$' THEN
                RAISE EXCEPTION 'invalid admin audit action';
            END IF;
            IF p_target_id IS NOT NULL AND
               (length(p_target_id) NOT BETWEEN 1 AND 160 OR
                p_target_id ~ '[[:cntrl:]]') THEN
                RAISE EXCEPTION 'invalid admin audit target';
            END IF;
            IF p_reason IS NULL OR length(p_reason) NOT BETWEEN 8 AND 500 OR
               p_reason ~ '[[:cntrl:]]' THEN
                RAISE EXCEPTION 'invalid admin audit reason';
            END IF;
            IF p_correlation_id IS NULL OR
               length(p_correlation_id) NOT BETWEEN 3 AND 160 OR
               p_correlation_id ~ '[[:cntrl:]]' THEN
                RAISE EXCEPTION 'invalid admin audit correlation';
            END IF;
            IF p_result IS NULL OR
               p_result NOT IN ('attempted', 'succeeded', 'failed') THEN
                RAISE EXCEPTION 'invalid admin audit result';
            END IF;

            SELECT state.last_sequence_id, state.last_hash
              INTO v_previous_sequence, v_previous_hash
              FROM admin_audit.chain_state AS state
             WHERE state.singleton
             FOR UPDATE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'admin audit chain state is missing';
            END IF;

            v_sequence := v_previous_sequence + 1;
            v_payload := jsonb_build_object(
                'action', p_action,
                'correlation_id', p_correlation_id,
                'event_id', v_event_id::text,
                'occurred_at', to_char(
                    v_occurred_at AT TIME ZONE 'UTC',
                    'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                ),
                'operator_id', p_operator_id,
                'reason', p_reason,
                'result', p_result,
                'sequence_id', v_sequence,
                'target_id', p_target_id
            )::text;
            v_row_hash := encode(
                sha256(convert_to(v_previous_hash || ':' || v_payload, 'UTF8')),
                'hex'
            );

            INSERT INTO admin_audit.entries (
                sequence_id, event_id, operator_id, action, target_id, reason,
                correlation_id, occurred_at, result, previous_hash, row_hash
            ) VALUES (
                v_sequence, v_event_id, p_operator_id, p_action, p_target_id,
                p_reason, p_correlation_id, v_occurred_at, p_result,
                v_previous_hash, v_row_hash
            );
            UPDATE admin_audit.chain_state
               SET last_sequence_id = v_sequence,
                   last_hash = v_row_hash
             WHERE singleton;

            RETURN QUERY SELECT v_sequence, v_event_id, v_occurred_at, v_row_hash;
        END
        $function$;
        ALTER FUNCTION admin_audit.append_entry(text, text, text, text, text, text)
            OWNER TO bookpile_admin_audit_owner;

        CREATE FUNCTION admin_audit.verify_chain()
        RETURNS TABLE (rows_verified bigint, last_sequence_id bigint, last_hash text)
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_expected_sequence bigint;
            v_expected_hash text;
            v_payload text;
            v_computed_hash text;
            v_count bigint := 0;
            v_entry record;
            v_state_sequence bigint;
            v_state_hash text;
        BEGIN
            -- Hold the chain head stable so a concurrent append cannot commit
            -- between the entries snapshot and the final-state comparison.
            SELECT state.last_sequence_id, state.last_hash
              INTO v_state_sequence, v_state_hash
              FROM admin_audit.chain_state AS state
             WHERE state.singleton
             FOR SHARE;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'admin audit chain state is missing';
            END IF;
            SELECT checkpoint.pruned_through_sequence_id,
                   checkpoint.pruned_through_hash
              INTO v_expected_sequence, v_expected_hash
              FROM admin_audit.retention_checkpoint AS checkpoint
             WHERE checkpoint.singleton;
            IF NOT FOUND THEN
                RAISE EXCEPTION 'admin audit retention checkpoint is missing';
            END IF;

            FOR v_entry IN
                SELECT * FROM admin_audit.entries ORDER BY sequence_id
            LOOP
                IF v_entry.sequence_id <> v_expected_sequence + 1 OR
                   v_entry.previous_hash <> v_expected_hash THEN
                    RAISE EXCEPTION 'admin audit chain linkage failed at sequence %',
                        v_entry.sequence_id;
                END IF;
                v_payload := jsonb_build_object(
                    'action', v_entry.action,
                    'correlation_id', v_entry.correlation_id,
                    'event_id', v_entry.event_id::text,
                    'occurred_at', to_char(
                        v_entry.occurred_at AT TIME ZONE 'UTC',
                        'YYYY-MM-DD"T"HH24:MI:SS.US"Z"'
                    ),
                    'operator_id', v_entry.operator_id,
                    'reason', v_entry.reason,
                    'result', v_entry.result,
                    'sequence_id', v_entry.sequence_id,
                    'target_id', v_entry.target_id
                )::text;
                v_computed_hash := encode(
                    sha256(convert_to(v_expected_hash || ':' || v_payload, 'UTF8')),
                    'hex'
                );
                IF v_entry.row_hash <> v_computed_hash THEN
                    RAISE EXCEPTION 'admin audit row hash failed at sequence %',
                        v_entry.sequence_id;
                END IF;
                v_expected_sequence := v_entry.sequence_id;
                v_expected_hash := v_entry.row_hash;
                v_count := v_count + 1;
            END LOOP;

            IF v_state_sequence <> v_expected_sequence OR
               v_state_hash <> v_expected_hash THEN
                RAISE EXCEPTION 'admin audit chain state does not match the ledger';
            END IF;
            RETURN QUERY SELECT v_count, v_expected_sequence, v_expected_hash;
        END
        $function$;
        ALTER FUNCTION admin_audit.verify_chain()
            OWNER TO bookpile_admin_audit_owner;

        CREATE FUNCTION admin_audit.prune_expired()
        RETURNS TABLE (
            rows_deleted bigint,
            pruned_through_sequence_id bigint,
            pruned_through_hash text
        )
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog
        AS $function$
        DECLARE
            v_cutoff timestamptz := clock_timestamp() - interval '365 days';
            v_sequence bigint;
            v_hash text;
            v_deleted bigint;
        BEGIN
            -- Serialize retention with append_entry, and verify the complete
            -- chain before authorizing any prefix deletion.
            PERFORM 1 FROM admin_audit.chain_state WHERE singleton FOR UPDATE;
            PERFORM * FROM admin_audit.verify_chain();
            SELECT entry.sequence_id, entry.row_hash
              INTO v_sequence, v_hash
              FROM admin_audit.entries AS entry
             WHERE entry.sequence_id < COALESCE(
                       (
                           SELECT min(recent.sequence_id)
                             FROM admin_audit.entries AS recent
                            WHERE recent.occurred_at >= v_cutoff
                       ),
                       9223372036854775807
                   )
             ORDER BY entry.sequence_id DESC
             LIMIT 1;
            IF NOT FOUND THEN
                RETURN QUERY
                SELECT 0::bigint,
                       checkpoint.pruned_through_sequence_id,
                       checkpoint.pruned_through_hash::text
                  FROM admin_audit.retention_checkpoint AS checkpoint
                 WHERE checkpoint.singleton;
                RETURN;
            END IF;
            DELETE FROM admin_audit.entries WHERE sequence_id <= v_sequence;
            GET DIAGNOSTICS v_deleted = ROW_COUNT;
            UPDATE admin_audit.retention_checkpoint
               SET pruned_through_sequence_id = v_sequence,
                   pruned_through_hash = v_hash,
                   pruned_at = clock_timestamp()
             WHERE singleton;
            RETURN QUERY SELECT v_deleted, v_sequence, v_hash;
        END
        $function$;
        ALTER FUNCTION admin_audit.prune_expired()
            OWNER TO bookpile_admin_audit_owner;

        REVOKE ALL ON SCHEMA admin_audit FROM PUBLIC;
        REVOKE ALL ON ALL TABLES IN SCHEMA admin_audit FROM PUBLIC;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA admin_audit FROM PUBLIC;
        REVOKE ALL ON ALL FUNCTIONS IN SCHEMA admin_audit FROM PUBLIC;
        GRANT USAGE ON SCHEMA admin_audit TO
            bookpile_admin_audit_writer,
            bookpile_admin_audit_reader,
            bookpile_admin_audit_backup,
            bookpile_admin_audit_verifier,
            bookpile_admin_audit_retention;
        GRANT EXECUTE ON FUNCTION
            admin_audit.append_entry(text, text, text, text, text, text)
            TO bookpile_admin_audit_writer;
        GRANT SELECT ON admin_audit.entries
            TO bookpile_admin_audit_reader;
        GRANT SELECT ON ALL TABLES IN SCHEMA admin_audit
            TO bookpile_admin_audit_backup;
        GRANT EXECUTE ON FUNCTION admin_audit.verify_chain()
            TO bookpile_admin_audit_verifier;
        GRANT EXECUTE ON FUNCTION admin_audit.prune_expired()
            TO bookpile_admin_audit_retention;

        GRANT USAGE ON SCHEMA public TO bookpile_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public
            TO bookpile_runtime;
        GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public
            TO bookpile_runtime;
        REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM bookpile_runtime;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO bookpile_runtime;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            GRANT USAGE, SELECT ON SEQUENCES TO bookpile_runtime;
        """
    )


def downgrade() -> None:
    connection = op.get_bind()
    count = connection.scalar(text("SELECT count(*) FROM admin_audit.entries"))
    if count:
        raise RuntimeError("immutable admin audit rows must be preserved before downgrade")
    op.execute(
        """
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE SELECT, INSERT, UPDATE, DELETE ON TABLES FROM bookpile_runtime;
        ALTER DEFAULT PRIVILEGES IN SCHEMA public
            REVOKE USAGE, SELECT ON SEQUENCES FROM bookpile_runtime;
        REVOKE ALL ON ALL TABLES IN SCHEMA public FROM bookpile_runtime;
        REVOKE ALL ON ALL SEQUENCES IN SCHEMA public FROM bookpile_runtime;
        REVOKE USAGE ON SCHEMA public FROM bookpile_runtime;
        """
    )
    op.execute("DROP SCHEMA admin_audit CASCADE")
    for role in reversed(_ROLES):
        op.execute(f'DROP ROLE IF EXISTS "{role}"')
