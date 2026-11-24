"""Narrow database client for the privileged administration audit ledger."""

import argparse
import json
import os
from pathlib import Path
import socket
import socketserver
import stat
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import SQLAlchemyError

from ..admin_audit import (
    AdminAuditError,
    append,
    parse_host_evidence_access,
    prune_expired,
    verify,
)


def _engine():
    database_url = os.environ.get("BOOKPILE_ADMIN_AUDIT_DATABASE_URL", "")
    if not database_url.startswith(("postgresql://", "postgresql+psycopg://")):
        raise AdminAuditError("the admin audit PostgreSQL credential is unavailable")
    return create_engine(database_url, pool_pre_ping=True, pool_size=1, max_overflow=0)


def _read_payload() -> object:
    content = sys.stdin.read(65_537)
    if not content or len(content) > 65_536:
        raise AdminAuditError("admin audit input is empty or too large")
    try:
        return json.loads(content)
    except json.JSONDecodeError as exc:
        raise AdminAuditError("admin audit input is not valid JSON") from exc


def _execute(command: str, payload: object | None = None) -> dict[str, object]:
    engine = _engine()
    try:
        if command == "append-host-evidence-access":
            return append(engine, parse_host_evidence_access(payload))
        if command == "verify":
            return verify(engine)
        if command == "retain":
            return prune_expired(engine)
        raise AdminAuditError("admin audit command is not allowed")
    finally:
        engine.dispose()


class _AuditRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        try:
            content = self.rfile.readline(65_537)
            if not content or len(content) > 65_536 or not content.endswith(b"\n"):
                raise AdminAuditError("admin audit request is invalid")
            request = json.loads(content)
            if not isinstance(request, dict) or set(request) != {"command", "payload"}:
                raise AdminAuditError("admin audit request is invalid")
            if request["command"] != "append-host-evidence-access":
                raise AdminAuditError("admin audit socket command is not allowed")
            result = _execute(request["command"], request["payload"])
            response = {"ok": True, "result": result}
        except Exception:
            response = {"error": "admin audit request rejected", "ok": False}
        self.wfile.write(
            json.dumps(response, sort_keys=True, separators=(",", ":")).encode()
            + b"\n"
        )


class _AuditServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def _serve(socket_path: Path) -> None:
    parent = socket_path.parent
    if not parent.is_dir() or parent.is_symlink():
        raise AdminAuditError("admin audit socket directory is unavailable")
    if socket_path.exists() or socket_path.is_symlink():
        details = socket_path.lstat()
        if not stat.S_ISSOCK(details.st_mode) or details.st_uid != os.getuid():
            raise AdminAuditError("refusing an unsafe existing audit socket")
        socket_path.unlink()
    previous_umask = os.umask(0o177)
    try:
        with _AuditServer(str(socket_path), _AuditRequestHandler) as server:
            os.chmod(socket_path, 0o600)
            server.serve_forever()
    finally:
        os.umask(previous_umask)
        if socket_path.exists() and stat.S_ISSOCK(socket_path.lstat().st_mode):
            socket_path.unlink()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "command", choices=("append-host-evidence-access", "verify", "retain", "serve")
    )
    parser.add_argument(
        "--socket", type=Path, default=Path("/run/bookpile-admin-audit/audit.sock")
    )
    args = parser.parse_args()
    try:
        if args.command == "serve":
            _serve(args.socket)
            return 0
        input_payload = (
            _read_payload() if args.command == "append-host-evidence-access" else None
        )
        payload = _execute(args.command, input_payload)
        print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)
        return 0
    except AdminAuditError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (OSError, SQLAlchemyError):
        print("admin audit database operation failed", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
