from datetime import UTC, datetime, timedelta
import json
from pathlib import Path
import subprocess
import sys

from sqlalchemy.orm import Session

from bookpile_server.defensive_metrics import aggregate_lease_conflicts
from bookpile_server.models import SecurityEvent


REVISION = "a" * 40


def test_metric_collector_has_a_bounded_systemd_schedule() -> None:
    systemd = Path(__file__).resolve().parents[1] / "deploy" / "systemd"
    service = (systemd / "bookpile-defensive-metrics.service.example").read_text()
    timer = (systemd / "bookpile-defensive-metrics.timer.example").read_text()

    assert "ExecStart=/usr/local/sbin/bookpile-defensive-metrics" in service
    assert "--window-minutes 15" in service
    assert "TimeoutStartSec=2m" in service
    assert "OnCalendar=*:4/15" in timer
    assert "Persistent=true" in timer


def test_database_aggregate_contains_only_safe_labels_and_counts(
    session: Session,
) -> None:
    now = datetime.now(UTC)
    session.add_all(
        (
            SecurityEvent(
                event_type="operation_lease_blocked",
                occurred_at=now - timedelta(minutes=1),
                ip_address="192.0.2.5",
                details={
                    "scope": "portable_export_library",
                    "deployment_revision": REVISION,
                    "private": "must-not-escape",
                },
            ),
            SecurityEvent(
                event_type="operation_lease_blocked",
                occurred_at=now - timedelta(minutes=1),
                details={"scope": "unsafe scope", "deployment_revision": REVISION},
            ),
            SecurityEvent(
                event_type="operation_lease_observed",
                occurred_at=now - timedelta(hours=2),
                details={
                    "scope": "portable_export_user",
                    "deployment_revision": REVISION,
                },
            ),
        )
    )
    session.commit()

    result = aggregate_lease_conflicts(
        session, window=timedelta(minutes=15), now=now
    )

    assert result["total"] == 1
    assert result["groups"] == [
        {
            "count": 1,
            "event_type": "operation_lease_blocked",
            "policy": "operation_lease",
            "revision": REVISION,
            "scope": "portable_export_library",
        }
    ]
    serialized = json.dumps(result)
    assert "192.0.2.5" not in serialized
    assert "must-not-escape" not in serialized


def test_host_collector_aggregates_without_emitting_identity_or_content(
    tmp_path: Path,
) -> None:
    now = datetime.now(UTC).timestamp()
    api_fixture = tmp_path / "api.jsonl"
    edge_fixture = tmp_path / "edge.jsonl"
    database_fixture = tmp_path / "database.json"
    api_events = [
        {
            "event": "http_request",
            "route": "/api/v1/books/{book_id}",
            "status": status,
            "client_key": client,
            "deployment_revision": REVISION,
            "private": "secret-title",
        }
        for status, client in (
            (429, "1" * 16),
            (503, "1" * 16),
            (500, "2" * 16),
            *((422, "3" * 16) for _ in range(5)),
        )
    ]
    api_fixture.write_text(
        "\n".join(json.dumps(event) for event in api_events), encoding="utf-8"
    )
    edge_fixture.write_text(
        "\n".join(
            (
                json.dumps(
                    {
                        "ts": now,
                        "event_class": "scanner_probe",
                        "policy_scope": "scanner_probe",
                        "deployment_revision": REVISION,
                        "request": {"remote_ip": "192.0.2.9"},
                    }
                ),
                json.dumps(
                    {
                        "ts": now,
                        "event_class": "temporary_ban",
                        "policy_scope": "edge_temporary_ban",
                        "deployment_revision": REVISION,
                    }
                ),
            )
        ),
        encoding="utf-8",
    )
    database_fixture.write_text(
        json.dumps(
            {
                "groups": [
                    {
                        "count": 2,
                        "event_type": "operation_lease_blocked",
                        "policy": "operation_lease",
                        "revision": REVISION,
                        "scope": "portable_export_library",
                    }
                ],
                "metric": "lease_conflicts",
                "total": 2,
                "window_seconds": 900,
            }
        ),
        encoding="utf-8",
    )
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "collect-defensive-metrics.py"
    )

    completed = subprocess.run(
        [
            sys.executable,
            str(script),
            "--api-fixture",
            str(api_fixture),
            "--edge-fixture",
            str(edge_fixture),
            "--database-fixture",
            str(database_fixture),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)

    assert payload["metrics"]["http_429"]["total"] == 1
    assert payload["metrics"]["http_503"]["total"] == 1
    assert payload["metrics"]["http_5xx"]["total"] == 2
    assert payload["metrics"]["repeated_validation_failures"]["total"] == 5
    assert payload["metrics"]["scanner_probes"]["total"] == 1
    assert payload["metrics"]["temporary_bans"]["total"] == 1
    assert payload["metrics"]["lease_conflicts"]["total"] == 2
    serialized = completed.stdout
    for forbidden in (
        "1" * 16,
        "3" * 16,
        "192.0.2.9",
        "secret-title",
        "remote_ip",
    ):
        assert forbidden not in serialized


def test_host_collector_fails_closed_on_invalid_source(tmp_path: Path) -> None:
    script = (
        Path(__file__).resolve().parents[1]
        / "deploy"
        / "collect-defensive-metrics.py"
    )
    api_fixture = tmp_path / "api.jsonl"
    edge_fixture = tmp_path / "edge.jsonl"
    database_fixture = tmp_path / "database.json"
    api_fixture.write_text("ordinary startup message\n", encoding="utf-8")
    edge_fixture.write_text("", encoding="utf-8")
    database_fixture.write_text(
        json.dumps(
            {
                "groups": [],
                "metric": "lease_conflicts",
                "total": 0,
                "window_seconds": 900,
            }
        ),
        encoding="utf-8",
    )
    command = [
        sys.executable,
        str(script),
        "--api-fixture",
        str(api_fixture),
        "--edge-fixture",
        str(edge_fixture),
        "--database-fixture",
        str(database_fixture),
    ]

    missing_api = subprocess.run(command, capture_output=True, text=True)
    assert missing_api.returncode == 1
    assert missing_api.stdout == ""
    assert "SourceValidationError" in missing_api.stderr

    api_fixture.write_text(
        json.dumps(
            {
                "event": "http_request",
                "route": "/health/live",
                "status": 200,
                "client_key": "a" * 16,
                "deployment_revision": REVISION,
            }
        ),
        encoding="utf-8",
    )
    database_fixture.write_text("{}", encoding="utf-8")

    invalid_database = subprocess.run(command, capture_output=True, text=True)
    assert invalid_database.returncode == 1
    assert invalid_database.stdout == ""
    assert "SourceValidationError" in invalid_database.stderr

    database_fixture.write_text(
        json.dumps(
            {
                "groups": [],
                "metric": "lease_conflicts",
                "total": 0,
                "window_seconds": 900,
            }
        ),
        encoding="utf-8",
    )
    edge_fixture.write_text("not-json", encoding="utf-8")

    malformed_edge = subprocess.run(command, capture_output=True, text=True)
    assert malformed_edge.returncode == 1
    assert malformed_edge.stdout == ""
    assert "SourceValidationError" in malformed_edge.stderr
