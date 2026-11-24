#!/usr/bin/env python3
"""Fail closed unless the running process uses the least-privilege A3 role."""

import json
import sys

from sqlalchemy import create_engine, text

from bookpile_server.config import get_settings


def main() -> int:
    engine = create_engine(get_settings().database_url, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            row = connection.execute(
                text(
                    "SELECT current_user, rolsuper, rolcreatedb, rolcreaterole, "
                    "rolreplication, rolbypassrls, "
                    "pg_has_role(current_user, 'bookpile_runtime', 'member') AS runtime, "
                    "has_schema_privilege(current_user, 'admin_audit', 'USAGE') AS audit_usage "
                    "FROM pg_roles WHERE rolname = current_user"
                )
            ).mappings().one()
        healthy = bool(
            row["runtime"]
            and not row["rolsuper"]
            and not row["rolcreatedb"]
            and not row["rolcreaterole"]
            and not row["rolreplication"]
            and not row["rolbypassrls"]
            and not row["audit_usage"]
        )
        print(
            json.dumps(
                {
                    "admin_audit_access": False,
                    "application_role": row["current_user"],
                    "healthy": healthy,
                    "runtime_member": bool(row["runtime"]),
                    "superuser": bool(row["rolsuper"]),
                },
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        return 0 if healthy else 1
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
