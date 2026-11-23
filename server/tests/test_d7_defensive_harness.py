from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run-d7-defensive-harness.py"
)


def load_harness():
    spec = importlib.util.spec_from_file_location("d7_harness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_covers_every_required_d7_scenario() -> None:
    harness = load_harness()

    assert [scenario.name for scenario in harness.SCENARIOS] == [
        "normal_navigation_and_api_bursts",
        "scanner_paths_and_health_exemptions",
        "forwarded_identity_and_ip_parsing",
        "fixed_window_expiry_and_privacy",
        "lease_loss_and_disconnected_exports",
        "shared_clients_and_multiple_library_owners",
        "unauthorized_identifiers_and_state_isolation",
        "secret_and_private_value_redaction",
    ]
    targets = "\n".join(
        target for scenario in harness.SCENARIOS for target in scenario.tests
    )
    for required in (
        "test_general_api_limits.py",
        "test_caddy_health_classification.py",
        "test_runtime.py",
        "test_rate_limits.py",
        "test_operation_leases.py",
        "test_costly_operation_leases.py",
        "test_mutation_limits.py",
        "test_authorization_cross_library_matrix.py",
        "test_defensive_metrics.py",
    ):
        assert required in targets


def test_runner_continues_after_failure_and_emits_only_aggregate_results(
    tmp_path: Path,
) -> None:
    harness = load_harness()
    commands: list[tuple[str, ...]] = []

    def fake_runner(command, cwd):
        assert cwd == tmp_path
        commands.append(tuple(command))
        return 1 if "server/tests/test_operation_leases.py" in command else 0

    report = harness.run_harness(
        repo_root=tmp_path,
        revision="a" * 40,
        runner=fake_runner,
    )

    assert len(commands) == len(harness.SCENARIOS)
    assert report["healthy"] is False
    assert report["privacy"] == "aggregate_only"
    assert report["deployment_revision"] == "a" * 40
    assert report["scenario_count"] == 8
    assert [
        item["name"] for item in report["scenarios"] if item["status"] == "failed"
    ] == ["lease_loss_and_disconnected_exports"]
    serialized = json.dumps(report)
    assert "server/tests" not in serialized
    assert "198.51.100.24" not in serialized
    assert "secret-token" not in serialized


def test_revision_must_be_a_full_lowercase_commit(tmp_path: Path) -> None:
    harness = load_harness()

    assert harness._revision(tmp_path, "b" * 40) == "b" * 40
    with pytest.raises(ValueError, match="40-character"):
        harness._revision(tmp_path, "abc123")
    with pytest.raises(ValueError, match="40-character"):
        harness._revision(tmp_path, "A" * 40)
