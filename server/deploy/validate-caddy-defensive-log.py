#!/usr/bin/env python3
"""Fail-closed schema validation for BOOKPILE's minimized D6 Caddy log."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
from collections import Counter
from pathlib import Path


ALLOWED_FIELDS = {
    "ts",
    "level",
    "logger",
    "msg",
    "deployment_revision",
    "health_class",
    "defensive_decision",
    "client_ip",
}
HEALTH_CLASSES = {"live", "ready", "other"}
REVISION = re.compile(r"[0-9a-f]{40}")


class DefensiveLogValidationError(ValueError):
    """Raised when one event violates the intentionally tiny D6 schema."""


def validate_event(event: object) -> dict[str, object]:
    if not isinstance(event, dict):
        raise DefensiveLogValidationError("defensive event is not an object")
    if set(event) != ALLOWED_FIELDS:
        raise DefensiveLogValidationError("defensive event fields are not exact")
    if not isinstance(event["ts"], (int, float)):
        raise DefensiveLogValidationError("defensive event timestamp is invalid")
    if event["level"] not in {"info", "error"}:
        raise DefensiveLogValidationError("defensive event level is unexpected")
    if event["logger"] != "http.log.access.d6_defensive":
        raise DefensiveLogValidationError("defensive event logger is unexpected")
    if event["msg"] != "handled request":
        raise DefensiveLogValidationError("defensive event message is unexpected")
    revision = event["deployment_revision"]
    if not isinstance(revision, str) or REVISION.fullmatch(revision) is None:
        raise DefensiveLogValidationError("deployment revision is invalid")
    if event["health_class"] not in HEALTH_CLASSES:
        raise DefensiveLogValidationError("health class is unexpected")
    if event["defensive_decision"] != "observed":
        raise DefensiveLogValidationError("defensive decision is unexpected")
    client_ip = event["client_ip"]
    if not isinstance(client_ip, str):
        raise DefensiveLogValidationError("client IP is invalid")
    try:
        ipaddress.ip_address(client_ip)
    except ValueError as exc:
        raise DefensiveLogValidationError("client IP is invalid") from exc
    return event


def validate_lines(lines: list[str]) -> Counter[str]:
    classes: Counter[str] = Counter()
    for line_number, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise DefensiveLogValidationError(
                f"line {line_number} is not JSON"
            ) from exc
        validated = validate_event(event)
        classes[str(validated["health_class"])] += 1
    return classes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    args = parser.parse_args()
    try:
        lines = args.log.read_text(encoding="utf-8").splitlines()
        classes = validate_lines(lines)
    except (OSError, DefensiveLogValidationError) as exc:
        parser.error(str(exc))
    print(json.dumps({"health_classes": dict(sorted(classes.items()))}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
