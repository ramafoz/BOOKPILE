#!/usr/bin/env python3
"""Run privacy-safe, fail-closed D7 checks against BOOKPILE staging."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


REVISION_PATTERN = re.compile(r"^[0-9a-f]{40}$")
SAFE_PHASE = {"baseline", "before_enforcement_change", "after_enforcement_change"}
EXPECTED_METRICS = {
    "http_429",
    "http_503",
    "http_5xx",
    "lease_conflicts",
    "repeated_validation_failures",
    "scanner_probes",
    "temporary_bans",
}
EVIDENCE_ROOT = Path("/var/lib/bookpile/d7-evidence")


class CheckFailure(RuntimeError):
    pass


CommandRunner = Callable[[Sequence[str], str | None], str]
HttpGetter = Callable[[str, bool], tuple[int, object | None]]


class _RejectRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, request, file_pointer, code, message, headers, new_url
    ):
        return None


@dataclass(frozen=True)
class ExpectedModes:
    live: str
    ready: str
    scanner: str
    volume: str


@dataclass(frozen=True)
class Context:
    repo_root: Path
    origin: str
    expected_revision: str
    modes: ExpectedModes
    run: CommandRunner
    get: HttpGetter


def _run(command: Sequence[str], stdin: str | None = None) -> str:
    return subprocess.run(
        command,
        check=True,
        input=stdin,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


def _get(url: str, expect_json: bool) -> tuple[int, object | None]:
    request = urllib.request.Request(url, headers={"User-Agent": "BOOKPILE-D7/1"})
    try:
        opener = urllib.request.build_opener(_RejectRedirects)
        with opener.open(request, timeout=15) as response:
            body = response.read(65537)
            if len(body) > 65536:
                raise CheckFailure("Oversized HTTP response")
            if not expect_json:
                return response.status, None
            return response.status, json.loads(body)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise CheckFailure("Public endpoint check failed") from exc


def _json_object(raw: str, description: str) -> dict[str, Any]:
    lines = [line.strip() for line in raw.splitlines() if line.strip()]
    if not lines:
        raise CheckFailure(f"Missing {description}")
    try:
        value = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise CheckFailure(f"Malformed {description}") from exc
    if not isinstance(value, dict):
        raise CheckFailure(f"Invalid {description}")
    return value


def _deployment_identity_and_health(context: Context) -> dict[str, object]:
    live_status, live = context.get(f"{context.origin}/health/live", True)
    ready_status, ready = context.get(f"{context.origin}/health/ready", True)
    if live_status != 200 or ready_status != 200:
        raise CheckFailure("Health endpoint is not successful")
    if not isinstance(live, dict) or not isinstance(ready, dict):
        raise CheckFailure("Invalid health payload")
    if live != {"status": "alive", "revision": context.expected_revision}:
        raise CheckFailure("Unexpected liveness payload")
    if ready.get("status") != "ready" or ready.get("revision") != context.expected_revision:
        raise CheckFailure("Unexpected readiness payload")
    if ready.get("checks") != {"database": "ready", "private_objects": "ready"}:
        raise CheckFailure("Readiness dependency failed")
    harness_revision = context.run(("git", "rev-parse", "HEAD"), None).strip()
    if REVISION_PATTERN.fullmatch(harness_revision) is None:
        raise CheckFailure("Invalid harness revision")
    return {"harness_revision": harness_revision, "public_health": "ready"}


def _public_navigation(context: Context) -> dict[str, object]:
    status, _ = context.get(f"{context.origin}/", False)
    if status != 200:
        raise CheckFailure("Public navigation failed")
    return {"root_status": 200}


def _application_containers(context: Context) -> dict[str, object]:
    expected = {
        "bookpile-production-api-1": True,
        "bookpile-production-db-1": True,
        "bookpile-production-email-worker-1": False,
        "bookpile-production-web-1": False,
    }
    for container, requires_health in expected.items():
        state = _json_object(
            context.run(
                ("docker", "inspect", "--format", "{{json .State}}", container),
                None,
            ),
            "container state",
        )
        if state.get("Status") != "running":
            raise CheckFailure("Required container is not running")
        if requires_health and state.get("Health", {}).get("Status") != "healthy":
            raise CheckFailure("Required container is not healthy")
    return {"healthy_containers": len(expected)}


def _deep_reconciliation(context: Context) -> dict[str, object]:
    payload = _json_object(
        context.run(
            (
                "docker",
                "compose",
                "--env-file",
                "server/.env.staging",
                "-f",
                "server/compose.production.yaml",
                "--profile",
                "operations",
                "run",
                "--rm",
                "maintenance",
                "bookpile-maintenance",
                "check",
                "--deep",
            ),
            None,
        ),
        "deep reconciliation result",
    )
    counters = payload.get("counters")
    if payload.get("healthy") is not True or not isinstance(counters, dict):
        raise CheckFailure("Deep reconciliation is unhealthy")
    if counters.get("private_objects_expected") != counters.get("private_objects_stored"):
        raise CheckFailure("Private object count mismatch")
    for key in (
        "private_objects_mismatched",
        "private_objects_missing",
        "private_objects_orphaned",
        "account_deletions_overdue",
        "library_deletions_overdue",
        "email_failed",
        "email_overdue",
    ):
        if counters.get(key) != 0:
            raise CheckFailure("Deep reconciliation counter is nonzero")
    return {"private_objects_consistent": True}


def _expected_jails(modes: ExpectedModes) -> set[str]:
    jails = {
        f"bookpile-health-live-{modes.live}",
        f"bookpile-health-ready-{modes.ready}",
    }
    if modes.scanner != "inactive":
        jails.add(f"bookpile-scanner-{modes.scanner}")
    if modes.volume != "inactive":
        jails.add(f"bookpile-edge-volume-{modes.volume}")
    return jails


def _edge_enforcement(context: Context) -> dict[str, object]:
    state = _json_object(
        context.run(
            ("bash", "server/deploy/install-bookpile-edge-enforcement.sh", "--check"),
            None,
        ),
        "edge enforcement state",
    )
    expected_state = {
        "firewall": "active"
        if "enforce" in vars(context.modes).values()
        else "absent",
        "live": context.modes.live,
        "ready": context.modes.ready,
        "scanner": context.modes.scanner,
        "volume": context.modes.volume,
        "ssh_port_matched": False,
    }
    if state != expected_state:
        raise CheckFailure("Unexpected edge enforcement state")

    status = context.run(("fail2ban-client", "status"), None)
    jail_line = next(
        (line for line in status.splitlines() if "Jail list:" in line), None
    )
    if jail_line is None:
        raise CheckFailure("Missing Fail2ban jail list")
    actual_jails = {
        item.strip()
        for item in jail_line.split("Jail list:", 1)[1].split(",")
        if item.strip()
    }
    expected_jails = _expected_jails(context.modes)
    if actual_jails != expected_jails:
        raise CheckFailure("Unexpected Fail2ban jail set")

    if expected_state["firewall"] == "active":
        nft_payload = context.run(("nft", "-j", "list", "table", "inet", "bookpile"), None)
        validation = _json_object(
            context.run(
                ("python3", "server/deploy/validate-bookpile-nftables.py"),
                nft_payload,
            ),
            "nftables validation",
        )
        if validation.get("ssh_port_matched") is not False or validation.get("rules") != 4:
            raise CheckFailure("Unsafe nftables validation")
    return {
        "firewall": expected_state["firewall"],
        "jail_count": len(expected_jails),
        "live": context.modes.live,
        "ready": context.modes.ready,
        "scanner": context.modes.scanner,
        "volume": context.modes.volume,
    }


def _defensive_metrics(context: Context) -> dict[str, object]:
    payload = _json_object(
        context.run(
            ("/usr/local/sbin/bookpile-defensive-metrics", "--window-minutes", "15"),
            None,
        ),
        "defensive metric result",
    )
    metrics = payload.get("metrics")
    if (
        payload.get("privacy") != "aggregate_only"
        or payload.get("window_minutes") != 15
        or not isinstance(metrics, dict)
        or set(metrics) != EXPECTED_METRICS
    ):
        raise CheckFailure("Invalid defensive metric result")
    for metric in metrics.values():
        if not isinstance(metric, dict) or not isinstance(metric.get("total"), int):
            raise CheckFailure("Invalid defensive metric aggregate")
    return {"metric_count": len(metrics), "privacy": "aggregate_only"}


def _host_services(context: Context) -> dict[str, object]:
    for unit in (
        "docker.service",
        "containerd.service",
        "fail2ban.service",
        "bookpile-defensive-metrics.timer",
    ):
        if context.run(("systemctl", "is-active", unit), None).strip() != "active":
            raise CheckFailure("Required host unit is inactive")
    if context.run(("systemctl", "--failed", "--no-legend", "--plain"), None).strip():
        raise CheckFailure("Host has failed systemd units")
    return {"active_units": 4, "failed_units": 0}


def _privacy_sources(context: Context) -> dict[str, object]:
    payload = _json_object(
        context.run(
            (
                "python3",
                "server/deploy/validate-caddy-defensive-log.py",
                "/var/log/bookpile/defensive-events.log",
            ),
            None,
        ),
        "defensive log validation",
    )
    classes = payload.get("health_classes")
    if not isinstance(classes, dict) or not classes:
        raise CheckFailure("Defensive log has no validated classes")
    if set(classes) - {"live", "ready", "other"}:
        raise CheckFailure("Defensive log contains an unexpected class")
    return {"defensive_log": "validated", "privacy": "aggregate_only"}


SCENARIOS: tuple[tuple[str, Callable[[Context], dict[str, object]]], ...] = (
    ("deployment_identity_and_health", _deployment_identity_and_health),
    ("public_navigation", _public_navigation),
    ("application_containers", _application_containers),
    ("deep_reconciliation", _deep_reconciliation),
    ("edge_enforcement", _edge_enforcement),
    ("defensive_metrics", _defensive_metrics),
    ("host_services", _host_services),
    ("privacy_sources", _privacy_sources),
)


def run_harness(context: Context, phase: str) -> dict[str, object]:
    if phase not in SAFE_PHASE:
        raise ValueError("Invalid D7 staging phase")
    started = time.monotonic()
    results: list[dict[str, object]] = []
    harness_revision = "unknown"
    for name, check in SCENARIOS:
        scenario_started = time.monotonic()
        try:
            evidence = check(context)
            status = "passed"
            if name == "deployment_identity_and_health":
                harness_revision = str(evidence["harness_revision"])
        except (CheckFailure, OSError, subprocess.SubprocessError, TypeError, ValueError):
            evidence = {}
            status = "failed"
        results.append(
            {
                "name": name,
                "status": status,
                "duration_ms": round((time.monotonic() - scenario_started) * 1000),
                "evidence": evidence,
            }
        )
    report = {
        "schema_version": 1,
        "generated_at": datetime.now(UTC).isoformat(),
        "profile": "staging",
        "phase": phase,
        "harness_revision": harness_revision,
        "deployment_revision": context.expected_revision,
        "privacy": "aggregate_only",
        "healthy": all(item["status"] == "passed" for item in results),
        "scenario_count": len(results),
        "duration_ms": round((time.monotonic() - started) * 1000),
        "scenarios": results,
    }
    serialized = json.dumps(report, sort_keys=True)
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
    ):
        if forbidden in serialized.lower():
            raise CheckFailure("Private field escaped into D7 report")
    return report


def _write_evidence(report: dict[str, object], evidence_root: Path) -> Path:
    if evidence_root.is_symlink():
        raise CheckFailure("D7 evidence root must not be a symlink")
    evidence_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    metadata = evidence_root.stat()
    if not evidence_root.is_dir() or (
        hasattr(os, "geteuid") and metadata.st_uid != os.geteuid()
    ):
        raise CheckFailure("Unsafe D7 evidence root")
    os.chmod(evidence_root, 0o700)
    generated = str(report["generated_at"]).replace(":", "-").replace("+", "_")
    filename = (
        f"{report['phase']}-{report['deployment_revision']}-{generated}.json"
    )
    destination = evidence_root / filename
    report["evidence_file"] = filename
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
        json.dump(report, stream, sort_keys=True, separators=(",", ":"))
        stream.write("\n")
    return destination


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the BOOKPILE D7 staging profile.")
    parser.add_argument("--phase", required=True, choices=sorted(SAFE_PHASE))
    parser.add_argument("--expected-revision", required=True)
    parser.add_argument("--origin", default="https://staging.bookpile.gal")
    parser.add_argument("--expected-live", choices=("observe", "enforce"), default="enforce")
    parser.add_argument("--expected-ready", choices=("observe", "enforce"), default="enforce")
    parser.add_argument(
        "--expected-scanner", choices=("inactive", "observe", "enforce"), default="enforce"
    )
    parser.add_argument(
        "--expected-volume", choices=("inactive", "observe", "enforce"), default="enforce"
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if getattr(os, "geteuid", lambda: 1)() != 0:
        print("D7 staging harness must run as root.", file=sys.stderr)
        return 2
    if REVISION_PATTERN.fullmatch(args.expected_revision) is None:
        print("A full lowercase deployed revision is required.", file=sys.stderr)
        return 2
    if args.origin != "https://staging.bookpile.gal":
        print("The D7 staging profile only accepts the canonical staging origin.", file=sys.stderr)
        return 2
    context = Context(
        repo_root=Path(__file__).resolve().parents[2],
        origin=args.origin,
        expected_revision=args.expected_revision,
        modes=ExpectedModes(
            live=args.expected_live,
            ready=args.expected_ready,
            scanner=args.expected_scanner,
            volume=args.expected_volume,
        ),
        run=_run,
        get=_get,
    )
    os.chdir(context.repo_root)
    try:
        report = run_harness(context, args.phase)
        _write_evidence(report, EVIDENCE_ROOT)
    except (CheckFailure, OSError, ValueError) as exc:
        print(f"D7 staging harness configuration error: {type(exc).__name__}", file=sys.stderr)
        return 2
    print(json.dumps(report, sort_keys=True, separators=(",", ":")), flush=True)
    return 0 if report["healthy"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
