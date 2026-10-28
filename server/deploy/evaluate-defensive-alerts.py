#!/usr/bin/env python3
"""Evaluate aggregate D5 metrics and signal the current severity externally."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re
import subprocess
import sys


THRESHOLDS = {
    "http_429": (25, 100),
    "http_503": (1, 5),
    "http_5xx": (5, 20),
    "lease_conflicts": (1, 5),
    "repeated_validation_failures": (10, 25),
    "scanner_probes": (10, 60),
    "temporary_bans": (1, 5),
}
SAFE_ROUTE = re.compile(r"^(?:/[-A-Za-z0-9_{}./:*]+|unmatched)$")
SAFE_SCOPE = re.compile(r"^[a-z0-9_:-]{1,80}$")
SAFE_REVISION = re.compile(r"^[a-f0-9]{7,64}$")
SEVERITIES = {"healthy": 0, "warning": 1, "critical": 2}
CONFIG_NAMES = {
    ("warning", "open"): "healthchecks-defensive-warning-open.curl",
    ("warning", "recover"): "healthchecks-defensive-warning-recovery.curl",
    ("critical", "open"): "healthchecks-defensive-critical-open.curl",
    ("critical", "recover"): "healthchecks-defensive-critical-recovery.curl",
}


class AlertValidationError(RuntimeError):
    pass


def _read_payload() -> dict[str, object]:
    try:
        payload = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        raise AlertValidationError("Metric input is not valid JSON") from exc
    if not isinstance(payload, dict) or set(payload) != {
        "generated_at",
        "metrics",
        "privacy",
        "validation_repeat_count",
        "window_minutes",
    }:
        raise AlertValidationError("Metric input must be an object")
    if payload.get("privacy") != "aggregate_only":
        raise AlertValidationError("Metric input is not aggregate-only")
    if payload.get("window_minutes") != 15:
        raise AlertValidationError("Alert policy requires a 15-minute window")
    if payload.get("validation_repeat_count") != 5:
        raise AlertValidationError("Metric input has an invalid repeat threshold")
    metrics = payload.get("metrics")
    if not isinstance(metrics, dict) or set(metrics) != set(THRESHOLDS):
        raise AlertValidationError("Metric input has an unexpected metric set")
    sanitized_metrics = {}
    for name, metric in metrics.items():
        if not isinstance(metric, dict):
            raise AlertValidationError(f"Metric {name} is invalid")
        if set(metric) != {"groups", "policy", "total"}:
            raise AlertValidationError(f"Metric {name} has unexpected fields")
        total = metric.get("total")
        if not isinstance(total, int) or isinstance(total, bool) or total < 0:
            raise AlertValidationError(f"Metric {name} has an invalid total")
        groups = metric.get("groups")
        if not isinstance(groups, list):
            raise AlertValidationError(f"Metric {name} has invalid groups")
        sanitized_groups = [_safe_group(name, group) for group in groups]
        if sum(group["count"] for group in sanitized_groups) != total:
            raise AlertValidationError(f"Metric {name} has an inconsistent total")
        policy = metric.get("policy")
        expected_policy = {
            "http_429": "application_http",
            "http_503": "application_http",
            "http_5xx": "application_http",
            "lease_conflicts": "operation_lease",
            "repeated_validation_failures": "five_422_per_client_in_window",
            "scanner_probes": "caddy_edge",
            "temporary_bans": "caddy_edge",
        }[name]
        if policy != expected_policy:
            raise AlertValidationError(f"Metric {name} has an invalid policy")
        sanitized_metrics[name] = {
            "groups": sanitized_groups,
            "policy": policy,
            "total": total,
        }
    generated_at_value = payload.get("generated_at")
    if not isinstance(generated_at_value, str):
        raise AlertValidationError("Metric input has no generation time")
    try:
        generated_at = datetime.fromisoformat(generated_at_value)
    except ValueError as exc:
        raise AlertValidationError("Metric generation time is invalid") from exc
    if generated_at.tzinfo is None:
        raise AlertValidationError("Metric generation time has no timezone")
    return {
        "generated_at": generated_at.astimezone(UTC).isoformat(),
        "metrics": sanitized_metrics,
        "privacy": "aggregate_only",
        "validation_repeat_count": 5,
        "window_minutes": 15,
    }


def _safe_group(name: str, value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        raise AlertValidationError(f"Metric {name} has an invalid group")
    expected_fields = {"count", "revision", "scope"}
    if name == "repeated_validation_failures":
        expected_fields.add("repeated_clients")
    if name == "lease_conflicts":
        expected_fields.update({"event_type", "policy"})
    if set(value) != expected_fields:
        raise AlertValidationError(f"Metric {name} group has unexpected fields")
    count = value.get("count")
    revision = value.get("revision")
    scope = value.get("scope")
    if (
        not isinstance(count, int)
        or isinstance(count, bool)
        or count < 1
        or not isinstance(revision, str)
        or SAFE_REVISION.fullmatch(revision) is None
        or not isinstance(scope, str)
        or (
            SAFE_ROUTE.fullmatch(scope) is None
            and SAFE_SCOPE.fullmatch(scope) is None
        )
    ):
        raise AlertValidationError(f"Metric {name} group is unsafe")
    result = {"count": count, "revision": revision, "scope": scope}
    if name == "repeated_validation_failures":
        repeated_clients = value.get("repeated_clients")
        if (
            not isinstance(repeated_clients, int)
            or isinstance(repeated_clients, bool)
            or repeated_clients < 1
        ):
            raise AlertValidationError("Repeated-validation group is invalid")
        result["repeated_clients"] = repeated_clients
    if name == "lease_conflicts":
        event_type = value.get("event_type")
        if (
            event_type not in {"operation_lease_blocked", "operation_lease_observed"}
            or value.get("policy") != "operation_lease"
        ):
            raise AlertValidationError("Lease-conflict group is invalid")
        result.update({"event_type": event_type, "policy": "operation_lease"})
    return result


def _evaluate(payload: dict[str, object]) -> tuple[str, list[dict[str, object]]]:
    metrics = payload["metrics"]
    assert isinstance(metrics, dict)
    severity = "healthy"
    active = []
    for name, (warning, critical) in THRESHOLDS.items():
        metric = metrics[name]
        assert isinstance(metric, dict)
        total = metric["total"]
        assert isinstance(total, int)
        metric_severity = (
            "critical" if total >= critical else "warning" if total >= warning else "healthy"
        )
        if metric_severity != "healthy":
            active.append(
                {
                    "critical_threshold": critical,
                    "metric": name,
                    "severity": metric_severity,
                    "total": total,
                    "warning_threshold": warning,
                }
            )
        if SEVERITIES[metric_severity] > SEVERITIES[severity]:
            severity = metric_severity
    return severity, active


def _notification(
    *,
    active: list[dict[str, object]],
    channel: str,
    generated_at: object,
    severity: str,
    signal: str,
) -> dict[str, object]:
    return {
        "active_metrics": active,
        "channel": channel,
        "event": "defensive_alert_signal",
        "generated_at": generated_at,
        "privacy": "aggregate_only",
        "severity": severity,
        "signal": signal,
        "window_minutes": 15,
    }


def _notify(
    *,
    active: list[dict[str, object]],
    channel: str,
    curl_bin: str,
    curl_prefix_arguments: list[str],
    generated_at: object,
    notification_directory: Path,
    severity: str,
    signal: str,
) -> None:
    action = "open" if signal == "failure" else "recover"
    config = notification_directory / CONFIG_NAMES[(channel, action)]
    if config.is_symlink() or not config.is_file():
        raise AlertValidationError(f"Missing {channel} {action} notification config")
    message = json.dumps(
        _notification(
            active=active,
            channel=channel,
            generated_at=generated_at,
            severity=severity,
            signal=signal,
        ),
        sort_keys=True,
        separators=(",", ":"),
    )
    subprocess.run(
        [curl_bin, *curl_prefix_arguments, "-q", "--config", str(config)],
        input=message,
        text=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notification-directory", default="/etc/bookpile")
    parser.add_argument("--curl-bin", default="/usr/bin/curl")
    parser.add_argument("--curl-prefix-argument", action="append", default=[])
    args = parser.parse_args()

    payload = _read_payload()
    severity, active = _evaluate(payload)
    signals = []
    print(json.dumps(payload, sort_keys=True, separators=(",", ":")), flush=True)

    def notify(channel: str, signal: str) -> None:
        _notify(
            active=active,
            channel=channel,
            curl_bin=args.curl_bin,
            curl_prefix_arguments=args.curl_prefix_argument,
            generated_at=payload.get("generated_at"),
            notification_directory=Path(args.notification_directory),
            severity=severity,
            signal=signal,
        )
        signals.append({"channel": channel, "signal": signal})

    if severity == "critical":
        notify("critical", "failure")
        notify("warning", "success")
    elif severity == "warning":
        notify("warning", "failure")
        notify("critical", "success")
    else:
        notify("warning", "success")
        notify("critical", "success")
    print(
        json.dumps(
            {
                "active_metrics": active,
                "event": "defensive_alert_evaluation",
                "privacy": "aggregate_only",
                "severity": severity,
                "signals": signals,
                "window_minutes": 15,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        AlertValidationError,
        OSError,
        subprocess.CalledProcessError,
    ) as exc:
        print(
            f"defensive alert evaluation failed: {type(exc).__name__}",
            file=sys.stderr,
        )
        raise SystemExit(1) from None
