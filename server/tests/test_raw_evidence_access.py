import gzip
import json
import os
import runpy
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "deploy"
    / "bookpile-raw-evidence-access.py"
)
MODULE = runpy.run_path(str(SCRIPT))
EvidenceAccessError = MODULE["EvidenceAccessError"]
execute = MODULE["execute"]
event_id = MODULE["event_id"]
list_normalized = MODULE["list_normalized"]
read_events = MODULE["read_events"]
reveal_one = MODULE["reveal_one"]
validate_context = MODULE["validate_context"]

REVISION = "0123456789abcdef0123456789abcdef01234567"
KEY = b"a" * 32
NOW = datetime(2026, 11, 23, 20, 0, tzinfo=UTC)


def _event(
    seconds: int,
    *,
    client_ip: str = "192.0.2.10",
    scanner: bool = False,
) -> dict[str, object]:
    event: dict[str, object] = {
        "client_ip": client_ip,
        "defensive_decision": "observed",
        "deployment_revision": REVISION,
        "health_class": "other" if scanner else "live",
        "level": "info",
        "logger": "http.log.access.d6_defensive",
        "msg": "handled request",
        "ts": (NOW + timedelta(seconds=seconds)).timestamp(),
    }
    if scanner:
        event.update(
            {
                "event_class": "scanner_probe",
                "policy_scope": "scanner_probe",
            }
        )
    return event


def _context() -> dict[str, object]:
    return {
        "end": NOW + timedelta(minutes=5),
        "incident": "INC-2026-0001",
        "operator": "bookpileadmin",
        "reason": "Investigate the correlated defensive alert window.",
        "start": NOW - timedelta(minutes=1),
    }


def test_normalized_list_never_discloses_client_addresses() -> None:
    result = list_normalized(
        [_event(0), _event(1, client_ip="2001:db8::10", scanner=True)],
        key=KEY,
        start=NOW - timedelta(seconds=1),
        end=NOW + timedelta(minutes=1),
    )

    assert result["result_count"] == 2
    assert result["privacy"] == "normalized_without_client_ip"
    serialized = json.dumps(result)
    assert "192.0.2.10" not in serialized
    assert "2001:db8::10" not in serialized
    assert all(len(item["event_id"]) == 64 for item in result["events"])


def test_reveal_requires_and_returns_exactly_one_retained_event() -> None:
    first = _event(0)
    second = _event(1, client_ip="192.0.2.11")
    context = _context()

    result = reveal_one(
        [first, second],
        key=KEY,
        start=context["start"],
        end=context["end"],
        requested_event_id=event_id(second, KEY),
    )

    assert result["result_count"] == 1
    assert result["privacy"] == "single_retained_client_ip"
    assert result["event"]["client_ip"] == "192.0.2.11"
    assert result["event"]["event_id"] == event_id(second, KEY)

    with pytest.raises(EvidenceAccessError, match="exactly one"):
        reveal_one(
            [first],
            key=KEY,
            start=context["start"],
            end=context["end"],
            requested_event_id="f" * 64,
        )


def test_access_is_audited_before_read_and_before_disclosure() -> None:
    records: list[dict[str, object]] = []
    order: list[str] = []
    context = _context()

    def write_audit(payload: dict[str, object]) -> None:
        order.append(f"audit:{payload['result']}")
        records.append(payload)

    def load_events() -> list[dict[str, object]]:
        order.append("read")
        return [_event(0)]

    result = execute(
        mode="reveal",
        key=KEY,
        load_events=load_events,
        requested_event_id=event_id(_event(0), KEY),
        write_audit=write_audit,
        **context,
    )

    assert result["event"]["client_ip"] == "192.0.2.10"
    assert order == ["audit:attempted", "read", "audit:succeeded"]
    assert [record["result"] for record in records] == ["attempted", "succeeded"]
    assert "client_ip" not in json.dumps(records)
    assert records[-1]["result_count"] == 1


def test_audit_failure_prevents_reading_raw_evidence() -> None:
    read = False

    def reject_audit(_payload: dict[str, object]) -> None:
        raise EvidenceAccessError("immutable admin audit recorder rejected access")

    def load_events() -> list[dict[str, object]]:
        nonlocal read
        read = True
        return [_event(0)]

    with pytest.raises(EvidenceAccessError, match="audit recorder rejected"):
        execute(
            mode="list",
            key=KEY,
            load_events=load_events,
            requested_event_id=None,
            write_audit=reject_audit,
            **_context(),
        )
    assert read is False


def test_failed_selection_is_recorded_without_disclosing_the_ip() -> None:
    records: list[dict[str, object]] = []
    context = _context()

    with pytest.raises(EvidenceAccessError, match="exactly one"):
        execute(
            mode="reveal",
            key=KEY,
            load_events=lambda: [_event(0)],
            requested_event_id="f" * 64,
            write_audit=records.append,
            **context,
        )

    assert [record["result"] for record in records] == ["attempted", "failed"]
    assert "192.0.2.10" not in json.dumps(records)


def test_access_rejects_wide_or_bulk_windows() -> None:
    context = _context()
    with pytest.raises(EvidenceAccessError, match="exceeds 15 minutes"):
        validate_context(
            **{
                **context,
                "start": NOW - timedelta(minutes=16),
            }
        )

    with pytest.raises(EvidenceAccessError, match="more than 20"):
        list_normalized(
            [_event(second) for second in range(21)],
            key=KEY,
            start=NOW - timedelta(seconds=1),
            end=NOW + timedelta(minutes=1),
        )


def test_modes_reject_incompatible_event_identifier_arguments() -> None:
    records: list[dict[str, object]] = []
    with pytest.raises(EvidenceAccessError, match="list does not accept"):
        execute(
            mode="list",
            key=KEY,
            load_events=lambda: [_event(0)],
            requested_event_id="f" * 64,
            write_audit=records.append,
            **_context(),
        )
    with pytest.raises(EvidenceAccessError, match="reveal requires"):
        execute(
            mode="reveal",
            key=KEY,
            load_events=lambda: [_event(0)],
            requested_event_id=None,
            write_audit=records.append,
            **_context(),
        )
    assert records == []

def test_reader_validates_active_and_compressed_rolls(tmp_path: Path) -> None:
    active = tmp_path / "defensive-events.log"
    rolled = tmp_path / "defensive-events-2026-11-22T00-00-00.000-time.log.gz"
    active.write_text(json.dumps(_event(1)) + "\n", encoding="utf-8")
    active.chmod(0o600)
    with gzip.open(rolled, "wt", encoding="utf-8") as stream:
        stream.write(json.dumps(_event(0, scanner=True)) + "\n")
    rolled.chmod(0o600)

    events = read_events(active)
    assert len(events) == 2
    assert {event.get("event_class") for event in events} == {None, "scanner_probe"}

    active.write_text("{not-json}\n", encoding="utf-8")
    with pytest.raises(EvidenceAccessError, match="is invalid"):
        read_events(active)

    if os.name == "posix":
        active.write_text(json.dumps(_event(1)) + "\n", encoding="utf-8")
        active.chmod(0o644)
        with pytest.raises(EvidenceAccessError, match="permissions are unsafe"):
            read_events(active)


def test_deployment_contract_has_no_arbitrary_source_or_export_argument() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'parser.add_argument("--source"' not in source
    assert 'parser.add_argument("--output"' not in source
    assert 'parser.add_argument("--ip"' not in source
    assert 'choices=("list", "reveal")' in source
    assert "os.geteuid() != 0" in source
