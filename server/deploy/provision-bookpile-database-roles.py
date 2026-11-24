#!/usr/bin/env python3
"""Provision fixed LOGIN identities for the reviewed PostgreSQL group roles."""

import json
import os
import sys
from urllib.parse import urlsplit

import psycopg
from psycopg import sql


ROLE_ENVIRONMENT = {
    "bookpile_app": ("BOOKPILE_DATABASE_APP_PASSWORD", "bookpile_runtime"),
    "bookpile_admin_audit_writer_login": (
        "BOOKPILE_DATABASE_ADMIN_AUDIT_WRITER_PASSWORD",
        "bookpile_admin_audit_writer",
    ),
    "bookpile_admin_audit_verifier_login": (
        "BOOKPILE_DATABASE_ADMIN_AUDIT_VERIFIER_PASSWORD",
        "bookpile_admin_audit_verifier",
    ),
    "bookpile_admin_audit_retention_login": (
        "BOOKPILE_DATABASE_ADMIN_AUDIT_RETENTION_PASSWORD",
        "bookpile_admin_audit_retention",
    ),
}
CONFIRMATION = "PROVISION-BOOKPILE-SEPARATE-DATABASE-ROLES"


def _password(name: str) -> str:
    value = os.environ.get(name, "")
    if len(value) < 32 or value.lower().startswith("replace-"):
        raise RuntimeError(f"{name} requires an independent password of at least 32 characters")
    return value


def main() -> int:
    if os.geteuid() != 0:
        print("database role provisioning requires root", file=sys.stderr)
        return 1
    if sys.argv != [sys.argv[0], "--confirm", CONFIRMATION]:
        print(f"Usage: {sys.argv[0]} --confirm {CONFIRMATION}", file=sys.stderr)
        return 2
    database_url = os.environ.get("BOOKPILE_DATABASE_MIGRATOR_URL", "")
    parsed = urlsplit(database_url.replace("postgresql+psycopg://", "postgresql://", 1))
    if parsed.scheme != "postgresql" or not parsed.hostname or not parsed.path.strip("/"):
        print("BOOKPILE_DATABASE_MIGRATOR_URL is invalid", file=sys.stderr)
        return 1
    passwords = {role: _password(variable) for role, (variable, _) in ROLE_ENVIRONMENT.items()}
    try:
        with psycopg.connect(database_url.replace("+psycopg", ""), autocommit=True) as connection:
            with connection.cursor() as cursor:
                attributes = cursor.execute(
                    "SELECT rolsuper, rolcreaterole FROM pg_roles WHERE rolname = current_user"
                ).fetchone()
                if attributes != (True, True):
                    raise RuntimeError("the migrator must be a PostgreSQL role administrator")
                backup = cursor.execute(
                    "SELECT rolsuper, rolcanlogin, rolinherit FROM pg_roles "
                    "WHERE rolname = 'bookpile_backup'"
                ).fetchone()
                if backup != (False, True, True):
                    raise RuntimeError(
                        "bookpile_backup must be an existing non-superuser INHERIT login"
                    )
                for role, (_, group) in ROLE_ENVIRONMENT.items():
                    cursor.execute(
                        sql.SQL(
                            "DO $role$ BEGIN IF NOT EXISTS "
                            "(SELECT 1 FROM pg_roles WHERE rolname = {}) THEN "
                            "CREATE ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                            "INHERIT NOREPLICATION NOBYPASSRLS; END IF; END $role$"
                        ).format(sql.Literal(role), sql.Identifier(role))
                    )
                    memberships = {
                        row[0]
                        for row in cursor.execute(
                            "SELECT parent.rolname FROM pg_auth_members membership "
                            "JOIN pg_roles member ON member.oid = membership.member "
                            "JOIN pg_roles parent ON parent.oid = membership.roleid "
                            "WHERE member.rolname = %s",
                            (role,),
                        ).fetchall()
                    }
                    if memberships - {group}:
                        raise RuntimeError(
                            f"{role} has unreviewed role memberships"
                        )
                    owned_objects = cursor.execute(
                        "SELECT ("
                        "  SELECT count(*) FROM pg_class object "
                        "  JOIN pg_roles owner ON owner.oid = object.relowner "
                        "  WHERE owner.rolname = %s"
                        ") + ("
                        "  SELECT count(*) FROM pg_namespace namespace "
                        "  JOIN pg_roles owner ON owner.oid = namespace.nspowner "
                        "  WHERE owner.rolname = %s"
                        ") + ("
                        "  SELECT count(*) FROM pg_proc routine "
                        "  JOIN pg_roles owner ON owner.oid = routine.proowner "
                        "  WHERE owner.rolname = %s"
                        ")",
                        (role, role, role),
                    ).fetchone()[0]
                    direct_grants = sum(
                        cursor.execute(
                            sql.SQL(
                                "SELECT count(*) FROM information_schema.{} "
                                "WHERE grantee = %s"
                            ).format(sql.Identifier(view)),
                            (role,),
                        ).fetchone()[0]
                        for view in (
                            "role_table_grants",
                            "role_routine_grants",
                            "role_usage_grants",
                        )
                    )
                    if owned_objects or direct_grants:
                        raise RuntimeError(
                            f"{role} owns objects or has unreviewed direct grants"
                        )
                    cursor.execute(
                        sql.SQL(
                            "ALTER ROLE {} LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
                            "INHERIT NOREPLICATION NOBYPASSRLS PASSWORD {}"
                        ).format(sql.Identifier(role), sql.Literal(passwords[role]))
                    )
                    cursor.execute(
                        sql.SQL("GRANT {} TO {}")
                        .format(sql.Identifier(group), sql.Identifier(role))
                    )
                cursor.execute(
                    "GRANT bookpile_admin_audit_backup TO bookpile_backup"
                )
        print(
            json.dumps(
                {"login_roles": sorted(ROLE_ENVIRONMENT), "passwords_exposed": False},
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except psycopg.Error:
        print("database role provisioning failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
