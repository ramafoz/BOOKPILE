#!/usr/bin/env python3
"""Evaluate BOOKPILE public-health edge thresholds without blocking traffic."""

from __future__ import annotations

import argparse
import ipaddress
import json
import runpy
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Iterable


WINDOW_SECONDS = 60
POLICIES = {"live": 120, "ready": 30}


class HealthObservationError(ValueError):
    """Raised when dry-run evidence is missing, malformed or unsafe."""


def _load_event_validator():
    validator_path = Path(__file__).with_name("validate-caddy-defensive-log.py")
    namespace = runpy.run_path(str(validator_path))
    return namespace["validate_event"], namespace["DefensiveLogValidationError"]


def _parse_lines(lines: Iterable[str]) -> Iterable[dict[str, object]]:
    validate_event, validation_error = _load_event_validator()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
            yield validate_event(event)
        except (json.JSONDecodeError, validation_error) as exc:
            raise HealthObservationError(
                f"defensive log line {line_number} is invalid"
            ) from exc


def evaluate(
    lines: Iterable[str], *, now: datetime
) -> dict[str, object]:
    if now.tzinfo is None:
        raise HealthObservationError("evaluation time must include a timezone")
    now = now.astimezone(UTC)
    now_timestamp = now.timestamp()
    cutoff = now_timestamp - WINDOW_SECONDS
    attempts: dict[str, Counter[str]] = {
        health_class: Counter() for health_class in POLICIES
    }
    revisions: dict[tuple[str, str], set[str]] = defaultdict(set)
    ignored_other = 0

    for event in _parse_lines(lines):
        timestamp = float(event["ts"])
        if timestamp > now_timestamp + 1:
            raise HealthObservationError("defensive event is from the future")
        if not cutoff < timestamp <= now_timestamp:
            continue
        health_class = str(event["health_class"])
        if health_class == "other":
            ignored_other += 1
            continue
        canonical_ip = ipaddress.ip_address(str(event["client_ip"])).compressed
        attempts[health_class][canonical_ip] += 1
        revisions[(health_class, canonical_ip)].add(
            str(event["deployment_revision"])
        )

    policies: dict[str, dict[str, object]] = {}
    for health_class, threshold in POLICIES.items():
        class_attempts = attempts[health_class]
        crossing = {
            client: count
            for client, count in class_attempts.items()
            if count > threshold
        }
        contributing_revisions = sorted(
            {
                revision
                for client in crossing
                for revision in revisions[(health_class, client)]
            }
        )
        policies[health_class] = {
            "attempts": sum(class_attempts.values()),
            "crossing_clients": len(crossing),
            "decision": "would_temporarily_ban" if crossing else "allow",
            "deployment_revisions": contributing_revisions,
            "max_attempts_per_client": max(class_attempts.values(), default=0),
            "threshold": threshold,
        }

    return {
        "generated_at": now.isoformat(),
        "ignored_other_events": ignored_other,
        "mode": "dry-run",
        "policies": policies,
        "privacy": "aggregate_only",
        "window_seconds": WINDOW_SECONDS,
    }


def _parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("time must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise argparse.ArgumentTypeError("time must include a timezone")
    return parsed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("logs", nargs="+", type=Path)
    parser.add_argument("--now", type=_parse_time, default=datetime.now(UTC))
    args = parser.parse_args()

    lines: list[str] = []
    try:
        for path in args.logs:
            if path.is_symlink() or not path.is_file():
                raise HealthObservationError("defensive log is missing or unsafe")
            lines.extend(path.read_text(encoding="utf-8").splitlines())
        result = evaluate(lines, now=args.now)
    except (OSError, HealthObservationError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
