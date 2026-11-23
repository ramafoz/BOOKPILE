#!/usr/bin/env python3
"""Incident-bound access to one minimized BOOKPILE defensive log source."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import hmac
import json
import math
import os
import re
import runpy
import stat
import subprocess
from collections.abc import Callable, Iterable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


SOURCE = Path("/var/log/bookpile/defensive-events.log")
KEY_PATH = Path("/etc/bookpile/raw-evidence-hmac.key")
AUDIT_COMMAND = Path("/usr/local/sbin/bookpile-admin-audit")
MAX_WINDOW = timedelta(minutes=15)
MAX_EVENTS = 20
INCIDENT = re.compile(r"INC-[A-Z0-9][A-Z0-9-]{2,63}")
OPERATOR = re.compile(r"[a-z_][a-z0-9_-]{0,31}")
EVENT_ID = re.compile(r"[0-9a-f]{64}")


class EvidenceAccessError(ValueError):
    """Raised before any evidence is disclosed when the contract is unsafe."""


def _load_event_validator() -> tuple[Callable[[object], dict[str, object]], type[Exception]]:
    namespace = runpy.run_path(
        str(Path(__file__).with_name("validate-caddy-defensive-log.py"))
    )
    return namespace["validate_event"], namespace["DefensiveLogValidationError"]


def parse_time(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise EvidenceAccessError("time must be ISO 8601") from exc
    if parsed.tzinfo is None:
        raise EvidenceAccessError("time must include a timezone")
    return parsed.astimezone(UTC)


def validate_context(
    *,
    operator: str,
    incident: str,
    reason: str,
    start: datetime,
    end: datetime,
) -> None:
    if OPERATOR.fullmatch(operator) is None:
        raise EvidenceAccessError("operator is invalid")
    if INCIDENT.fullmatch(incident) is None:
        raise EvidenceAccessError("incident identifier is invalid")
    if not 20 <= len(reason) <= 500 or any(ord(character) < 32 for character in reason):
        raise EvidenceAccessError("reason must contain 20-500 printable characters")
    if start.tzinfo is None or end.tzinfo is None:
        raise EvidenceAccessError("time range must include a timezone")
    start = start.astimezone(UTC)
    end = end.astimezone(UTC)
    if end <= start:
        raise EvidenceAccessError("time range must be increasing")
    if end - start > MAX_WINDOW:
        raise EvidenceAccessError("time range exceeds 15 minutes")
    if end > datetime.now(UTC) + timedelta(seconds=1):
        raise EvidenceAccessError("time range ends in the future")


def _discover_sources(active: Path) -> list[Path]:
    if active.is_symlink() or not active.is_file():
        raise EvidenceAccessError("defensive log is missing or unsafe")
    sources = sorted(active.parent.glob("defensive-events*.log*"))
    if not sources:
        raise EvidenceAccessError("defensive log source is missing")
    active_details = active.stat()
    expected_owner = (active_details.st_uid, active_details.st_gid)
    for source in sources:
        if source.is_symlink() or not source.is_file():
            raise EvidenceAccessError("defensive log roll is unsafe")
        details = source.stat()
        if (details.st_uid, details.st_gid) != expected_owner:
            raise EvidenceAccessError("defensive log ownership is inconsistent")
        if os.name == "posix" and stat.S_IMODE(details.st_mode) & 0o077:
            raise EvidenceAccessError("defensive log permissions are unsafe")
    return sources


def _identities(paths: Iterable[Path]) -> set[tuple[Path, int, int]]:
    return {(path, path.stat().st_dev, path.stat().st_ino) for path in paths}


def read_events(active: Path) -> list[dict[str, object]]:
    validate_event, validation_error = _load_event_validator()
    before = _discover_sources(active)
    before_identities = _identities(before)
    events: list[dict[str, object]] = []
    for source in before:
        opener = gzip.open if source.suffix == ".gz" else open
        with opener(source, "rt", encoding="utf-8") as stream:
            for line_number, line in enumerate(stream, start=1):
                if not line.strip():
                    continue
                try:
                    validated = validate_event(json.loads(line))
                    if isinstance(validated["ts"], bool) or not math.isfinite(
                        float(validated["ts"])
                    ):
                        raise EvidenceAccessError(
                            f"defensive log {source.name}:{line_number} has an invalid timestamp"
                        )
                    events.append(validated)
                except (json.JSONDecodeError, validation_error) as exc:
                    raise EvidenceAccessError(
                        f"defensive log {source.name}:{line_number} is invalid"
                    ) from exc
    after = _discover_sources(active)
    if before_identities != _identities(after):
        raise EvidenceAccessError("defensive logs rotated during access; retry")
    return events


def event_id(event: dict[str, object], key: bytes) -> str:
    canonical = json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("utf-8")
    return hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _normalized(event: dict[str, object], key: bytes) -> dict[str, object]:
    occurred_at = datetime.fromtimestamp(float(event["ts"]), UTC).isoformat()
    return {
        "deployment_revision": event["deployment_revision"],
        "event_class": event.get("event_class", "health_request"),
        "event_id": event_id(event, key),
        "health_class": event["health_class"],
        "occurred_at": occurred_at,
        "outcome": event["defensive_decision"],
    }


def select_events(
    events: Iterable[dict[str, object]],
    *,
    start: datetime,
    end: datetime,
) -> list[dict[str, object]]:
    start_timestamp = start.astimezone(UTC).timestamp()
    end_timestamp = end.astimezone(UTC).timestamp()
    selected = [
        event
        for event in events
        if start_timestamp <= float(event["ts"]) < end_timestamp
    ]
    if len(selected) > MAX_EVENTS:
        raise EvidenceAccessError(
            "time range contains more than 20 events; narrow the interval"
        )
    return sorted(selected, key=lambda event: float(event["ts"]))


def list_normalized(
    events: Iterable[dict[str, object]],
    *,
    key: bytes,
    start: datetime,
    end: datetime,
) -> dict[str, object]:
    selected = select_events(events, start=start, end=end)
    return {
        "events": [_normalized(event, key) for event in selected],
        "privacy": "normalized_without_client_ip",
        "result_count": len(selected),
    }


def reveal_one(
    events: Iterable[dict[str, object]],
    *,
    key: bytes,
    start: datetime,
    end: datetime,
    requested_event_id: str,
) -> dict[str, object]:
    if EVENT_ID.fullmatch(requested_event_id) is None:
        raise EvidenceAccessError("event identifier is invalid")
    selected = select_events(events, start=start, end=end)
    matches = [event for event in selected if event_id(event, key) == requested_event_id]
    if len(matches) != 1:
        raise EvidenceAccessError("exactly one retained event must match")
    normalized = _normalized(matches[0], key)
    normalized["client_ip"] = matches[0]["client_ip"]
    return {
        "event": normalized,
        "privacy": "single_retained_client_ip",
        "result_count": 1,
    }


def audit_record(
    payload: dict[str, object],
    *,
    command: Path = AUDIT_COMMAND,
) -> None:
    if command.is_symlink() or not command.is_file() or not os.access(command, os.X_OK):
        raise EvidenceAccessError("immutable admin audit recorder is unavailable")
    details = command.stat()
    if details.st_uid != 0 or stat.S_IMODE(details.st_mode) & 0o022:
        raise EvidenceAccessError("immutable admin audit recorder is unsafe")
    try:
        completed = subprocess.run(
            [str(command), "append-host-evidence-access"],
            input=json.dumps(payload, sort_keys=True, separators=(",", ":")),
            text=True,
            capture_output=True,
            check=False,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise EvidenceAccessError("immutable admin audit recorder failed") from exc
    if completed.returncode != 0:
        raise EvidenceAccessError("immutable admin audit recorder rejected access")


def _audit_payload(
    *,
    action: str,
    operator: str,
    incident: str,
    reason: str,
    start: datetime,
    end: datetime,
    result: str,
    target: str,
    result_count: int | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "action": action,
        "incident_id": incident,
        "occurred_at": datetime.now(UTC).isoformat(),
        "operator": operator,
        "reason": reason,
        "result": result,
        "source": "d6_defensive_events",
        "target": target,
        "window_end": end.astimezone(UTC).isoformat(),
        "window_start": start.astimezone(UTC).isoformat(),
    }
    if result_count is not None:
        payload["result_count"] = result_count
    return payload


def execute(
    *,
    mode: str,
    operator: str,
    incident: str,
    reason: str,
    start: datetime,
    end: datetime,
    key: bytes,
    load_events: Callable[[], Iterable[dict[str, object]]],
    requested_event_id: str | None,
    write_audit: Callable[[dict[str, object]], None],
) -> dict[str, object]:
    validate_context(
        operator=operator,
        incident=incident,
        reason=reason,
        start=start,
        end=end,
    )
    if len(key) < 32:
        raise EvidenceAccessError("event identifier key is too short")
    if mode not in {"list", "reveal"}:
        raise EvidenceAccessError("access mode is invalid")
    if mode == "list" and requested_event_id is not None:
        raise EvidenceAccessError("list does not accept an event identifier")
    if mode == "reveal" and requested_event_id is None:
        raise EvidenceAccessError("reveal requires one event identifier")
    target = requested_event_id or "bounded_normalized_list"
    write_audit(
        _audit_payload(
            action=f"raw_evidence_{mode}",
            operator=operator,
            incident=incident,
            reason=reason,
            start=start,
            end=end,
            result="attempted",
            target=target,
        )
    )
    try:
        if mode == "list":
            result = list_normalized(load_events(), key=key, start=start, end=end)
        else:
            result = reveal_one(
                load_events(),
                key=key,
                start=start,
                end=end,
                requested_event_id=requested_event_id,
            )
    except Exception:
        write_audit(
            _audit_payload(
                action=f"raw_evidence_{mode}",
                operator=operator,
                incident=incident,
                reason=reason,
                start=start,
                end=end,
                result="failed",
                target=target,
            )
        )
        raise
    write_audit(
        _audit_payload(
            action=f"raw_evidence_{mode}",
            operator=operator,
            incident=incident,
            reason=reason,
            start=start,
            end=end,
            result="succeeded",
            target=target,
            result_count=int(result["result_count"]),
        )
    )
    return result


def _read_key(path: Path) -> bytes:
    if path.is_symlink() or not path.is_file():
        raise EvidenceAccessError("event identifier key is missing or unsafe")
    details = path.stat()
    if details.st_uid != 0 or stat.S_IMODE(details.st_mode) != 0o600:
        raise EvidenceAccessError("event identifier key ownership or mode is unsafe")
    key = path.read_bytes()
    if len(key) < 32:
        raise EvidenceAccessError("event identifier key is too short")
    return key


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("list", "reveal"))
    parser.add_argument("--operator", required=True)
    parser.add_argument("--incident", required=True)
    parser.add_argument("--reason", required=True)
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--until", dest="end", required=True)
    parser.add_argument("--event-id")
    args = parser.parse_args()
    try:
        if os.geteuid() != 0:
            raise EvidenceAccessError("raw evidence access requires root")
        sudo_user = os.environ.get("SUDO_USER")
        if sudo_user and sudo_user != args.operator:
            raise EvidenceAccessError("operator does not match the sudo identity")
        start = parse_time(args.start)
        end = parse_time(args.end)
        key = _read_key(KEY_PATH)
        result = execute(
            mode=args.mode,
            operator=args.operator,
            incident=args.incident,
            reason=args.reason,
            start=start,
            end=end,
            key=key,
            load_events=lambda: read_events(SOURCE),
            requested_event_id=args.event_id,
            write_audit=audit_record,
        )
    except (OSError, EvidenceAccessError) as exc:
        parser.error(str(exc))
    print(json.dumps(result, sort_keys=True, separators=(",", ":")), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
