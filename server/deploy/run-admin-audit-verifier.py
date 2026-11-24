#!/usr/bin/env python3
"""Run A3 verification and send one privacy-safe external health signal."""

import json
from pathlib import Path
import subprocess
import sys


REPOSITORY = Path("/home/bookpileadmin/b")
COMPOSE = (
    "/usr/bin/docker",
    "compose",
    "--env-file",
    str(REPOSITORY / "server/.env.staging"),
    "-f",
    str(REPOSITORY / "server/compose.production.yaml"),
    "--profile",
    "administration",
    "run",
    "--rm",
    "admin-audit-verifier",
)
SUCCESS_CONFIG = Path("/etc/bookpile/healthchecks-admin-audit-recovery.curl")
FAILURE_CONFIG = Path("/etc/bookpile/healthchecks-admin-audit-open.curl")


def _signal(config: Path, payload: dict[str, object]) -> bool:
    try:
        completed = subprocess.run(
            ["/usr/bin/curl", "-q", "--config", str(config), "--data-binary", "@-"],
            input=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            text=True,
            capture_output=True,
            check=False,
            timeout=15,
        )
        return completed.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


def main() -> int:
    try:
        completed = subprocess.run(
            COMPOSE,
            cwd=REPOSITORY,
            text=True,
            capture_output=True,
            check=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        completed = subprocess.CompletedProcess(COMPOSE, 1, "", "")
    healthy = False
    rows_verified = None
    last_sequence_id = None
    if completed.returncode == 0:
        try:
            result = json.loads(completed.stdout.strip().splitlines()[-1])
            healthy = (
                isinstance(result, dict)
                and result.get("healthy") is True
                and result.get("privacy") == "aggregate_only"
                and isinstance(result.get("rows_verified"), int)
                and not isinstance(result.get("rows_verified"), bool)
                and isinstance(result.get("last_sequence_id"), int)
                and not isinstance(result.get("last_sequence_id"), bool)
            )
            if healthy:
                rows_verified = result["rows_verified"]
                last_sequence_id = result["last_sequence_id"]
        except (IndexError, json.JSONDecodeError):
            healthy = False
    payload = {
        "event": "admin_audit_integrity",
        "healthy": healthy,
        "last_sequence_id": last_sequence_id,
        "privacy": "aggregate_only",
        "rows_verified": rows_verified,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)
    delivered = _signal(SUCCESS_CONFIG if healthy else FAILURE_CONFIG, payload)
    return 0 if healthy and delivered else 1


if __name__ == "__main__":
    raise SystemExit(main())
