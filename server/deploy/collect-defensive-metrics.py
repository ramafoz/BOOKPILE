#!/usr/bin/env python3
"""Collect privacy-safe defensive aggregates from BOOKPILE's three log planes."""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime, timedelta
import gzip
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Iterable


SAFE_ROUTE = re.compile(r"^(?:/[-A-Za-z0-9_{}./:*]+|unmatched)$")
SAFE_SCOPE = re.compile(r"^[a-z0-9_:-]{1,80}$")
SAFE_REVISION = re.compile(r"^[a-f0-9]{7,64}$")
SAFE_CLIENT_KEY = re.compile(r"^[a-f0-9]{16}$")
VALIDATION_REPEAT_COUNT = 5


class SourceValidationError(RuntimeError):
    pass


def _json_lines(
    lines: Iterable[str], *, source: str, allow_unstructured: bool = False
) -> Iterable[dict[str, object]]:
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if not stripped.startswith("{"):
            if allow_unstructured:
                continue
            raise SourceValidationError(f"Invalid {source} record")
        try:
            value = json.loads(stripped)
        except (json.JSONDecodeError, TypeError) as exc:
            raise SourceValidationError(f"Malformed {source} JSON record") from exc
        if not isinstance(value, dict):
            raise SourceValidationError(f"Invalid {source} JSON record")
        yield value


def _safe_route(value: object) -> str | None:
    if isinstance(value, str) and SAFE_ROUTE.fullmatch(value):
        return value
    return None


def _safe_revision(value: object) -> str | None:
    if isinstance(value, str) and SAFE_REVISION.fullmatch(value):
        return value
    return None


def _groups(counter: Counter[tuple[str, str]]) -> list[dict[str, object]]:
    return [
        {"count": count, "revision": revision, "scope": scope}
        for (scope, revision), count in sorted(counter.items())
    ]


def aggregate_api(lines: Iterable[str]) -> dict[str, dict[str, object]]:
    counters: dict[str, Counter[tuple[str, str]]] = {
        "http_429": Counter(),
        "http_503": Counter(),
        "http_5xx": Counter(),
    }
    validations: defaultdict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    request_events = 0
    for event in _json_lines(
        lines, source="API journal", allow_unstructured=True
    ):
        if event.get("event") != "http_request":
            continue
        request_events += 1
        route = _safe_route(event.get("route"))
        revision = _safe_revision(event.get("deployment_revision"))
        status = event.get("status")
        client_key = event.get("client_key")
        if (
            route is None
            or revision is None
            or not isinstance(status, int)
            or status < 100
            or status > 599
            or not isinstance(client_key, str)
            or SAFE_CLIENT_KEY.fullmatch(client_key) is None
        ):
            raise SourceValidationError("Invalid minimized API request event")
        key = (route, revision)
        if status == 429:
            counters["http_429"][key] += 1
        if status == 503:
            counters["http_503"][key] += 1
        if status >= 500:
            counters["http_5xx"][key] += 1
        if status == 422:
            validations[key][client_key] += 1

    if request_events == 0:
        raise SourceValidationError("No minimized API request events in window")

    metrics = {
        name: {
            "groups": _groups(counter),
            "policy": "application_http",
            "total": sum(counter.values()),
        }
        for name, counter in counters.items()
    }
    repeated_groups = []
    repeated_total = 0
    for (scope, revision), clients in sorted(validations.items()):
        repeated_clients = sum(
            count >= VALIDATION_REPEAT_COUNT for count in clients.values()
        )
        if repeated_clients:
            repeated_events = sum(
                count for count in clients.values() if count >= VALIDATION_REPEAT_COUNT
            )
            repeated_total += repeated_events
            repeated_groups.append(
                {
                    "count": repeated_events,
                    "repeated_clients": repeated_clients,
                    "revision": revision,
                    "scope": scope,
                }
            )
    metrics["repeated_validation_failures"] = {
        "groups": repeated_groups,
        "policy": "five_422_per_client_in_window",
        "total": repeated_total,
    }
    return metrics


def aggregate_edge(
    lines: Iterable[str], *, cutoff: datetime
) -> dict[str, dict[str, object]]:
    counters = {"scanner_probes": Counter(), "temporary_bans": Counter()}
    for event in _json_lines(lines, source="Caddy edge log"):
        timestamp = event.get("ts")
        if not isinstance(timestamp, (int, float)):
            raise SourceValidationError("Caddy edge event has no timestamp")
        if datetime.fromtimestamp(timestamp, UTC) < cutoff:
            continue
        event_class = event.get("event_class")
        metric = {
            "scanner_probe": "scanner_probes",
            "temporary_ban": "temporary_bans",
        }.get(event_class)
        revision = _safe_revision(event.get("deployment_revision"))
        if metric is None:
            continue
        scope = event.get("policy_scope")
        if (
            revision is None
            or scope not in {"scanner_probe", "edge_temporary_ban"}
        ):
            raise SourceValidationError("Invalid defensive Caddy edge event")
        counters[metric][(scope, revision)] += 1
    return {
        name: {
            "groups": _groups(counter),
            "policy": "caddy_edge",
            "total": sum(counter.values()),
        }
        for name, counter in counters.items()
    }


def _read_lines(path: Path) -> Iterable[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as stream:
        yield from stream


def _run(command: list[str]) -> str:
    return subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout


def _database_metrics(args: argparse.Namespace) -> dict[str, object]:
    if args.database_fixture:
        return json.loads(Path(args.database_fixture).read_text(encoding="utf-8"))
    output = _run(
        [
            "docker", "compose", "--env-file", args.env_file,
            "-f", args.compose_file, "exec", "-T", "api",
            "bookpile-defensive-metrics", "--window-minutes", str(args.window_minutes),
        ]
    )
    return json.loads(output)


def _safe_database_groups(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list):
        raise SourceValidationError("Database metric groups are missing")
    result = []
    for group in value:
        if not isinstance(group, dict):
            raise SourceValidationError("Invalid database metric group")
        count = group.get("count")
        scope = group.get("scope")
        revision = _safe_revision(group.get("revision"))
        event_type = group.get("event_type")
        if (
            not isinstance(count, int)
            or count < 0
            or not isinstance(scope, str)
            or SAFE_SCOPE.fullmatch(scope) is None
            or revision is None
            or event_type
            not in {"operation_lease_blocked", "operation_lease_observed"}
        ):
            raise SourceValidationError("Unsafe database metric group")
        result.append(
            {
                "count": count,
                "event_type": event_type,
                "policy": "operation_lease",
                "revision": revision,
                "scope": scope,
            }
        )
    return result


def _api_lines(args: argparse.Namespace) -> Iterable[str]:
    if args.api_fixture:
        return Path(args.api_fixture).read_text(encoding="utf-8").splitlines()
    output = _run(
        [
            "journalctl", "--since", f"-{args.window_minutes} minutes",
            "-t", args.api_journal_tag, "-o", "cat", "--no-pager",
        ]
    )
    return output.splitlines()


def _edge_lines(args: argparse.Namespace) -> Iterable[str]:
    if args.edge_fixture:
        return Path(args.edge_fixture).read_text(encoding="utf-8").splitlines()
    mount_json = _run(["docker", "inspect", args.web_container])
    containers = json.loads(mount_json)
    mounts = containers[0].get("Mounts", []) if containers else []
    data_mount = next(
        (item.get("Source") for item in mounts if item.get("Destination") == "/data"),
        None,
    )
    if not isinstance(data_mount, str):
        raise RuntimeError("Could not resolve the web container /data mount")
    cutoff_timestamp = (
        datetime.now(UTC) - timedelta(minutes=args.window_minutes)
    ).timestamp()
    paths = sorted(
        path
        for path in Path(data_mount).glob("access*.log*")
        if path.stat().st_mtime >= cutoff_timestamp
    )
    return (line for path in paths for line in _read_lines(path))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--window-minutes", type=int, default=15)
    parser.add_argument("--env-file", default="server/.env.staging")
    parser.add_argument("--compose-file", default="server/compose.production.yaml")
    parser.add_argument(
        "--api-journal-tag", default="bookpile/bookpile-production-api-1"
    )
    parser.add_argument("--web-container", default="bookpile-production-web-1")
    parser.add_argument("--api-fixture")
    parser.add_argument("--edge-fixture")
    parser.add_argument("--database-fixture")
    args = parser.parse_args()
    if args.window_minutes < 1 or args.window_minutes > 1440:
        parser.error("--window-minutes must be between 1 and 1440")

    generated_at = datetime.now(UTC)
    database = _database_metrics(args)
    if (
        not isinstance(database, dict)
        or database.get("metric") != "lease_conflicts"
        or not isinstance(database.get("total"), int)
        or not isinstance(database.get("window_seconds"), int)
        or database.get("window_seconds") != args.window_minutes * 60
    ):
        raise SourceValidationError("Invalid database metric response")
    metrics = aggregate_api(_api_lines(args))
    metrics.update(
        aggregate_edge(
            _edge_lines(args),
            cutoff=generated_at - timedelta(minutes=args.window_minutes),
        )
    )
    database_groups = _safe_database_groups(database.get("groups"))
    database_total = sum(group["count"] for group in database_groups)
    if database_total != database["total"]:
        raise SourceValidationError("Inconsistent database metric total")
    metrics["lease_conflicts"] = {
        "groups": database_groups,
        "policy": "operation_lease",
        "total": database_total,
    }
    payload = {
        "generated_at": generated_at.isoformat(),
        "metrics": metrics,
        "privacy": "aggregate_only",
        "validation_repeat_count": VALIDATION_REPEAT_COUNT,
        "window_minutes": args.window_minutes,
    }
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
    ) as exc:
        print(
            f"defensive metric collection failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
