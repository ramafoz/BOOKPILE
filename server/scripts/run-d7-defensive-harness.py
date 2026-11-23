from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path


REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")


@dataclass(frozen=True)
class Scenario:
    name: str
    tests: tuple[str, ...]


SCENARIOS = (
    Scenario(
        "normal_navigation_and_api_bursts",
        (
            "server/tests/test_general_api_limits.py",
            "server/tests/test_mutation_limits.py::test_authenticated_mutations_are_limited_per_user",
            "server/tests/test_mutation_limits.py::test_read_only_post_preview_is_not_a_mutation",
        ),
    ),
    Scenario(
        "scanner_paths_and_health_exemptions",
        (
            "server/tests/test_caddy_health_classification.py",
            "server/tests/test_d6_edge_defence.py::test_scanner_observation_is_bounded_and_cannot_mutate_firewall",
            "server/tests/test_d6_edge_defence.py::test_scanner_enforcement_is_separate_bounded_and_disabled",
            "server/tests/test_d6_edge_defence.py::test_nftables_policy_cannot_match_ssh_or_internal_health",
        ),
    ),
    Scenario(
        "forwarded_identity_and_ip_parsing",
        (
            "server/tests/test_runtime.py::test_trusted_proxy_supplies_one_valid_client_address",
            "server/tests/test_runtime.py::test_untrusted_or_ambiguous_forwarded_address_fails_closed",
            "server/tests/test_general_api_limits.py::test_general_api_limit_uses_canonical_client_address",
            "server/tests/test_general_api_limits.py::test_general_api_limit_treats_ipv4_mapped_address_as_ipv4",
            "server/tests/test_general_api_limits.py::test_general_api_limit_uses_only_validated_forwarded_address",
        ),
    ),
    Scenario(
        "fixed_window_expiry_and_privacy",
        (
            "server/tests/test_rate_limits.py::test_rate_limit_uses_hashed_atomic_bucket_and_resets_window",
            "server/tests/test_rate_limits.py::test_defensive_modes_are_off_observable_and_privacy_preserving",
            "server/tests/test_rate_limits.py::test_defensive_enforcement_does_not_record_raw_ip_by_default",
        ),
    ),
    Scenario(
        "lease_loss_and_disconnected_exports",
        (
            "server/tests/test_operation_leases.py",
            "server/tests/test_costly_operation_leases.py",
            "server/tests/test_costly_operation_limits.py::test_post_acquisition_import_lease_loss_is_translated",
            "server/tests/test_costly_operation_limits.py::test_post_create_lease_failure_removes_completed_export",
        ),
    ),
    Scenario(
        "shared_clients_and_multiple_library_owners",
        (
            "server/tests/test_mutation_limits.py::test_library_limit_counts_only_active_members",
            "server/tests/test_mutation_limits.py::test_viewer_cannot_spend_owner_library_allowance",
            "server/tests/test_mutation_limits.py::test_users_have_independent_buckets_behind_one_client",
        ),
    ),
    Scenario(
        "unauthorized_identifiers_and_state_isolation",
        (
            "server/tests/test_authorization_cross_library_matrix.py::test_valid_foreign_uuids_are_generically_denied_without_state_change",
            "server/tests/test_catalogue_isolation.py::test_catalogue_api_does_not_leak_another_library",
            "server/tests/test_catalogue_isolation.py::test_unknown_library_is_hidden_from_authenticated_users",
        ),
    ),
    Scenario(
        "secret_and_private_value_redaction",
        (
            "server/tests/test_runtime.py::test_request_log_never_retains_credentials_tokens_bodies_or_catalogue_data",
            "server/tests/test_runtime.py::test_error_reporting_scrubber_keeps_stack_but_removes_private_context",
            "server/tests/test_defensive_metrics.py::test_database_aggregate_contains_only_safe_labels_and_counts",
            "server/tests/test_defensive_metrics.py::test_host_collector_aggregates_without_emitting_identity_or_content",
        ),
    ),
)


Runner = Callable[[Sequence[str], Path], int]


def _run(command: Sequence[str], cwd: Path) -> int:
    return subprocess.run(command, cwd=cwd, check=False).returncode


def _revision(repo_root: Path, supplied: str | None) -> str:
    candidate = (
        supplied
        or os.environ.get("GITHUB_SHA")
        or os.environ.get("BOOKPILE_SERVER_DEPLOYMENT_REVISION")
    )
    if candidate is None:
        candidate = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    if not REVISION_PATTERN.fullmatch(candidate):
        raise ValueError("A full 40-character lowercase Git revision is required.")
    return candidate


def run_harness(
    *,
    repo_root: Path,
    revision: str,
    selected_names: set[str] | None = None,
    runner: Runner = _run,
) -> dict[str, object]:
    selected = [
        scenario
        for scenario in SCENARIOS
        if selected_names is None or scenario.name in selected_names
    ]
    if not selected:
        raise ValueError("At least one D7 scenario must be selected.")

    started = time.monotonic()
    results: list[dict[str, object]] = []
    for scenario in selected:
        print(f"[D7] running {scenario.name}", file=sys.stderr, flush=True)
        scenario_started = time.monotonic()
        return_code = runner(
            (sys.executable, "-m", "pytest", "-q", *scenario.tests),
            repo_root,
        )
        results.append(
            {
                "name": scenario.name,
                "status": "passed" if return_code == 0 else "failed",
                "target_count": len(scenario.tests),
                "duration_ms": round((time.monotonic() - scenario_started) * 1000),
            }
        )

    return {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": "ci",
        "deployment_revision": revision,
        "privacy": "aggregate_only",
        "healthy": all(item["status"] == "passed" for item in results),
        "scenario_count": len(results),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "scenarios": results,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the BOOKPILE D7 defensive regression harness."
    )
    parser.add_argument("--revision")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--scenario",
        action="append",
        choices=[scenario.name for scenario in SCENARIOS],
        dest="scenarios",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    repo_root = Path(__file__).resolve().parents[2]
    try:
        revision = _revision(repo_root, args.revision)
        report = run_harness(
            repo_root=repo_root,
            revision=revision,
            selected_names=set(args.scenarios) if args.scenarios else None,
        )
    except (OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"D7 harness configuration error: {exc}", file=sys.stderr)
        return 2

    serialized = json.dumps(report, sort_keys=True, separators=(",", ":"))
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(serialized + "\n", encoding="utf-8")
    print(serialized, flush=True)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
