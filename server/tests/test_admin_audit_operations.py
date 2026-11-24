import importlib.util
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).parents[1]
SCRIPT = ROOT / "deploy" / "run-admin-audit-verifier.py"
TIMER = ROOT / "deploy" / "systemd" / "bookpile-admin-audit-verifier.timer.example"


def _module():
    specification = importlib.util.spec_from_file_location("audit_verifier", SCRIPT)
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_verifier_timer_is_staggered_from_existing_host_jobs() -> None:
    timer = TIMER.read_text(encoding="utf-8")

    assert "OnCalendar=*-*-* *:09/15:00 UTC" in timer
    assert "*:02/15:00" not in timer


def test_verifier_emits_only_aggregate_evidence(monkeypatch, capsys) -> None:
    module = _module()

    def run(command, **_kwargs):
        if tuple(command) == module.COMPOSE:
            return subprocess.CompletedProcess(
                command,
                0,
                json.dumps(
                    {
                        "healthy": True,
                        "last_hash": "a" * 64,
                        "last_sequence_id": 7,
                        "privacy": "aggregate_only",
                        "rows_verified": 7,
                    }
                ),
                "",
            )
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == 0
    output = json.loads(capsys.readouterr().out)
    assert output == {
        "event": "admin_audit_integrity",
        "healthy": True,
        "last_sequence_id": 7,
        "privacy": "aggregate_only",
        "rows_verified": 7,
    }
    assert "last_hash" not in output


def test_verifier_fails_closed_and_sends_failure(monkeypatch, capsys) -> None:
    module = _module()
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 1, "", "database detail")

    monkeypatch.setattr(module.subprocess, "run", run)
    assert module.main() == 1
    output = json.loads(capsys.readouterr().out)
    assert output["healthy"] is False
    assert output["rows_verified"] is None
    assert str(module.FAILURE_CONFIG) in calls[-1][0]
    assert "database detail" not in json.dumps(output)
