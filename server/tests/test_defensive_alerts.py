import json
from pathlib import Path
import subprocess
import sys

import pytest


THRESHOLDS = {
    "http_429": (25, 100),
    "http_503": (1, 5),
    "http_5xx": (5, 20),
    "lease_conflicts": (1, 5),
    "repeated_validation_failures": (10, 25),
    "scanner_probes": (10, 60),
    "temporary_bans": (1, 5),
}
REVISION = "a" * 40


def _groups(name: str, total: int) -> list[dict[str, object]]:
    if total == 0:
        return []
    group: dict[str, object] = {
        "count": total,
        "revision": REVISION,
        "scope": (
            "/api/v1/books/{book_id}"
            if name.startswith("http_") or name == "repeated_validation_failures"
            else "portable_export_library"
            if name == "lease_conflicts"
            else "scanner_probe"
            if name == "scanner_probes"
            else "edge_temporary_ban"
        ),
    }
    if name == "repeated_validation_failures":
        group["repeated_clients"] = 1
    if name == "lease_conflicts":
        group.update(
            {
                "event_type": "operation_lease_blocked",
                "policy": "operation_lease",
            }
        )
    return [group]


def _payload(**totals: int) -> str:
    return json.dumps(
        {
            "generated_at": "2026-10-28T08:00:00+00:00",
            "metrics": {
                name: {
                    "groups": _groups(name, totals.get(name, 0)),
                    "policy": {
                        "http_429": "application_http",
                        "http_503": "application_http",
                        "http_5xx": "application_http",
                        "lease_conflicts": "operation_lease",
                        "repeated_validation_failures": "five_422_per_client_in_window",
                        "scanner_probes": "caddy_edge",
                        "temporary_bans": "caddy_edge",
                    }[name],
                    "total": totals.get(name, 0),
                }
                for name in THRESHOLDS
            },
            "privacy": "aggregate_only",
            "validation_repeat_count": 5,
            "window_minutes": 15,
        }
    )


def _fixture(tmp_path: Path) -> tuple[list[str], Path]:
    script = Path(__file__).resolve().parents[1] / "deploy" / "evaluate-defensive-alerts.py"
    notification_directory = tmp_path / "notifications"
    notification_directory.mkdir()
    for name in (
        "healthchecks-defensive-warning-open.curl",
        "healthchecks-defensive-warning-recovery.curl",
        "healthchecks-defensive-critical-open.curl",
        "healthchecks-defensive-critical-recovery.curl",
    ):
        (notification_directory / name).write_text("fixture", encoding="utf-8")
    log = tmp_path / "curl.log"
    wrapper = tmp_path / "curl-wrapper.py"
    wrapper.write_text(
        """#!/usr/bin/env python3
import pathlib
import sys
config = pathlib.Path(sys.argv[-1]).name
body = sys.stdin.read()
with pathlib.Path(%r).open('a', encoding='utf-8') as stream:
    stream.write(config + '\\t' + body + '\\n')
""" % str(log),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(script),
        "--notification-directory",
        str(notification_directory),
        "--curl-bin",
        sys.executable,
        "--curl-prefix-argument",
        str(wrapper),
    ]
    return command, log


def _run(command: list[str], payload: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, input=payload, capture_output=True, text=True)


def _calls(log: Path) -> list[tuple[str, dict[str, object]]]:
    if not log.exists():
        return []
    result = []
    for line in log.read_text(encoding="utf-8").splitlines():
        config, body = line.split("\t", 1)
        result.append((config, json.loads(body)))
    return result


@pytest.mark.parametrize(
    ("metric", "warning", "critical"),
    [(name, values[0], values[1]) for name, values in THRESHOLDS.items()],
)
def test_exact_thresholds(metric: str, warning: int, critical: int, tmp_path: Path) -> None:
    command, _log = _fixture(tmp_path)

    below = _run(command, _payload(**{metric: warning - 1}))
    assert json.loads(below.stdout.splitlines()[-1])["severity"] == "healthy"
    at_warning = _run(command, _payload(**{metric: warning}))
    assert json.loads(at_warning.stdout.splitlines()[-1])["severity"] == "warning"

    at_critical = _run(command, _payload(**{metric: critical}))
    assert json.loads(at_critical.stdout.splitlines()[-1])["severity"] == "critical"


def test_signals_are_grouped_and_recovery_is_explicit(tmp_path: Path) -> None:
    command, log = _fixture(tmp_path)

    assert _run(command, _payload()).returncode == 0
    assert _run(command, _payload(http_429=25, scanner_probes=10)).returncode == 0
    assert _run(command, _payload(http_429=26)).returncode == 0
    assert _run(command, _payload(http_429=100, http_503=5)).returncode == 0
    assert _run(command, _payload(http_429=101)).returncode == 0
    assert _run(command, _payload()).returncode == 0

    calls = _calls(log)
    assert [name for name, _body in calls] == [
        "healthchecks-defensive-warning-recovery.curl",
        "healthchecks-defensive-critical-recovery.curl",
        "healthchecks-defensive-warning-open.curl",
        "healthchecks-defensive-critical-recovery.curl",
        "healthchecks-defensive-warning-open.curl",
        "healthchecks-defensive-critical-recovery.curl",
        "healthchecks-defensive-critical-open.curl",
        "healthchecks-defensive-warning-recovery.curl",
        "healthchecks-defensive-critical-open.curl",
        "healthchecks-defensive-warning-recovery.curl",
        "healthchecks-defensive-warning-recovery.curl",
        "healthchecks-defensive-critical-recovery.curl",
    ]
    warning = calls[2][1]
    assert warning["severity"] == "warning"
    assert {item["metric"] for item in warning["active_metrics"]} == {
        "http_429",
        "scanner_probes",
    }
    serialized = json.dumps(calls)
    for forbidden in ("client_key", "ip_address", "user_id", "library_id", "query"):
        assert forbidden not in serialized


def test_missing_notification_config_fails_closed(tmp_path: Path) -> None:
    command, _log = _fixture(tmp_path)
    missing = tmp_path / "notifications" / "healthchecks-defensive-critical-recovery.curl"
    missing.unlink()

    completed = _run(command, _payload())

    assert completed.returncode == 1
    assert "AlertValidationError" in completed.stderr


def test_invalid_or_non_aggregate_input_fails_closed(tmp_path: Path) -> None:
    command, _log = _fixture(tmp_path)
    payload = json.loads(_payload())
    payload["privacy"] = "contains_identity"

    completed = _run(command, json.dumps(payload))

    assert completed.returncode == 1
    assert "AlertValidationError" in completed.stderr


def test_unexpected_private_field_is_not_re_emitted(tmp_path: Path) -> None:
    command, _log = _fixture(tmp_path)
    payload = json.loads(_payload())
    payload["metrics"]["http_429"]["private"] = "must-not-escape"

    completed = _run(command, json.dumps(payload))

    assert completed.returncode == 1
    assert "must-not-escape" not in completed.stdout
    assert "must-not-escape" not in completed.stderr
