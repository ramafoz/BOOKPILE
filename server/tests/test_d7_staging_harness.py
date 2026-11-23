from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "scripts"
    / "run-d7-staging-harness.py"
)
DEPLOYED_REVISION = "a" * 40
HARNESS_REVISION = "b" * 40


def load_harness():
    spec = importlib.util.spec_from_file_location("d7_staging_harness", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def successful_runner(command, stdin):
    key = tuple(command)
    if key == ("git", "rev-parse", "HEAD"):
        return HARNESS_REVISION + "\n"
    if key[:3] == ("docker", "inspect", "--format"):
        container = key[-1]
        state = {"Status": "running"}
        if container in {"bookpile-production-api-1", "bookpile-production-db-1"}:
            state["Health"] = {"Status": "healthy"}
        return json.dumps(state)
    if key[:2] == ("docker", "compose"):
        return json.dumps(
            {
                "healthy": True,
                "counters": {
                    "private_objects_expected": 433,
                    "private_objects_stored": 433,
                    "private_objects_mismatched": 0,
                    "private_objects_missing": 0,
                    "private_objects_orphaned": 0,
                    "account_deletions_overdue": 0,
                    "library_deletions_overdue": 0,
                    "email_failed": 0,
                    "email_overdue": 0,
                },
            }
        )
    if key == (
        "bash",
        "server/deploy/install-bookpile-edge-enforcement.sh",
        "--check",
    ):
        return json.dumps(
            {
                "firewall": "active",
                "live": "enforce",
                "ready": "enforce",
                "scanner": "enforce",
                "volume": "enforce",
                "ssh_port_matched": False,
            }
        )
    if key == ("fail2ban-client", "status"):
        return (
            "Status\n|- Number of jail: 4\n`- Jail list: "
            "bookpile-edge-volume-enforce, bookpile-health-live-enforce, "
            "bookpile-health-ready-enforce, bookpile-scanner-enforce\n"
        )
    if key == ("nft", "-j", "list", "table", "inet", "bookpile"):
        return '{"nftables":[]}'
    if key == ("python3", "server/deploy/validate-bookpile-nftables.py"):
        assert stdin == '{"nftables":[]}'
        return json.dumps({"rules": 4, "ssh_port_matched": False})
    if key == ("/usr/local/sbin/bookpile-defensive-metrics", "--window-minutes", "15"):
        harness = load_harness()
        return json.dumps(
            {
                "privacy": "aggregate_only",
                "window_minutes": 15,
                "metrics": {
                    metric: {"total": 0, "groups": []}
                    for metric in harness.EXPECTED_METRICS
                },
            }
        )
    if key[:2] == ("systemctl", "is-active"):
        return "active\n"
    if key == ("systemctl", "--failed", "--no-legend", "--plain"):
        return ""
    if key == (
        "python3",
        "server/deploy/validate-caddy-defensive-log.py",
        "/var/log/bookpile/defensive-events.log",
    ):
        return json.dumps(
            {"health_classes": {"live": 4, "ready": 8, "other": 12}}
        )
    raise AssertionError(f"Unexpected command: {key}")


def successful_get(url, expect_json):
    if url.endswith("/health/live"):
        return 200, {"status": "alive", "revision": DEPLOYED_REVISION}
    if url.endswith("/health/ready"):
        return 200, {
            "status": "ready",
            "revision": DEPLOYED_REVISION,
            "checks": {"database": "ready", "private_objects": "ready"},
        }
    assert url == "https://staging.bookpile.gal/"
    assert expect_json is False
    return 200, None


def context(harness, runner=successful_runner):
    return harness.Context(
        repo_root=Path("/repo"),
        origin="https://staging.bookpile.gal",
        expected_revision=DEPLOYED_REVISION,
        modes=harness.ExpectedModes(
            live="enforce", ready="enforce", scanner="enforce", volume="enforce"
        ),
        run=runner,
        get=successful_get,
    )


def test_staging_profile_passes_all_bounded_scenarios() -> None:
    harness = load_harness()

    report = harness.run_harness(context(harness), "baseline")

    assert report["healthy"] is True
    assert report["profile"] == "staging"
    assert report["phase"] == "baseline"
    assert report["privacy"] == "aggregate_only"
    assert report["deployment_revision"] == DEPLOYED_REVISION
    assert report["harness_revision"] == HARNESS_REVISION
    assert report["scenario_count"] == 8
    assert all(item["status"] == "passed" for item in report["scenarios"])
    serialized = json.dumps(report, sort_keys=True).lower()
    for forbidden in (
        "client_key",
        "remote_ip",
        "ip_address",
        "authorization",
        "cookie",
        "query",
        "user_id",
        "library_id",
        "object_key",
        "198.51.100.24",
        "secret-token",
    ):
        assert forbidden not in serialized


def test_staging_profile_continues_after_a_failed_check() -> None:
    harness = load_harness()

    def failing_runner(command, stdin):
        if tuple(command)[:2] == ("docker", "compose"):
            return json.dumps({"healthy": False, "counters": {}})
        return successful_runner(command, stdin)

    report = harness.run_harness(context(harness, failing_runner), "baseline")

    assert report["healthy"] is False
    assert len(report["scenarios"]) == 8
    assert [
        item["name"] for item in report["scenarios"] if item["status"] == "failed"
    ] == ["deep_reconciliation"]


def test_edge_scenario_rejects_an_unexpected_jail() -> None:
    harness = load_harness()

    def unsafe_runner(command, stdin):
        if tuple(command) == ("fail2ban-client", "status"):
            return successful_runner(command, stdin).replace(
                "bookpile-scanner-enforce",
                "bookpile-scanner-enforce, bookpile-unreviewed",
            )
        return successful_runner(command, stdin)

    report = harness.run_harness(context(harness, unsafe_runner), "baseline")
    edge = next(item for item in report["scenarios"] if item["name"] == "edge_enforcement")

    assert edge["status"] == "failed"


def test_evidence_is_exclusive_and_contains_its_safe_filename(tmp_path: Path) -> None:
    harness = load_harness()
    report = harness.run_harness(context(harness), "before_enforcement_change")

    destination = harness._write_evidence(report, tmp_path / "evidence")

    stored = json.loads(destination.read_text(encoding="utf-8"))
    assert stored["evidence_file"] == destination.name
    assert DEPLOYED_REVISION in destination.name
    with pytest.raises(FileExistsError):
        harness._write_evidence(report, tmp_path / "evidence")


def test_revision_phase_and_origin_are_fail_closed() -> None:
    harness = load_harness()
    with pytest.raises(ValueError, match="phase"):
        harness.run_harness(context(harness), "maybe")
    assert harness.REVISION_PATTERN.fullmatch("A" * 40) is None
    assert harness.SAFE_PHASE == {
        "baseline",
        "before_enforcement_change",
        "after_enforcement_change",
    }
