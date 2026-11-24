from datetime import UTC, datetime, timedelta

import pytest

from bookpile_server.admin_audit import AdminAuditError, parse_host_evidence_access


def _payload() -> dict[str, object]:
    start = datetime(2026, 11, 24, 10, 0, tzinfo=UTC)
    return {
        "action": "list",
        "incident_id": "INC-2026-0001",
        "occurred_at": (start + timedelta(minutes=1)).isoformat(),
        "operator": "bookpileadmin",
        "reason": "Investigate the correlated defensive alert window.",
        "result": "attempted",
        "source": "d6_defensive_events",
        "target": "window:2026-11-24T10:00Z",
        "window_end": (start + timedelta(minutes=5)).isoformat(),
        "window_start": start.isoformat(),
    }


def test_host_evidence_payload_maps_only_minimized_fields() -> None:
    entry = parse_host_evidence_access(_payload())
    assert entry.operator_id == "bookpileadmin"
    assert entry.action == "host_evidence.list"
    assert entry.correlation_id == "INC-2026-0001"
    assert entry.result == "attempted"
    assert not hasattr(entry, "client_ip")


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("operator", "root\nforged"),
        ("action", "Reveal IP"),
        ("incident_id", "x"),
        ("reason", "short"),
        ("result", "success"),
        ("source", "access_log"),
        ("window_start", "2026-11-24T10:00:00"),
        ("result_count", 21),
    ],
)
def test_host_evidence_payload_rejects_invalid_values(field: str, value: object) -> None:
    payload = _payload()
    payload[field] = value
    with pytest.raises(AdminAuditError):
        parse_host_evidence_access(payload)


def test_host_evidence_payload_rejects_unknown_or_private_fields() -> None:
    for field in ("client_ip", "library_id", "notes"):
        payload = _payload()
        payload[field] = "192.0.2.10"
        with pytest.raises(AdminAuditError):
            parse_host_evidence_access(payload)
