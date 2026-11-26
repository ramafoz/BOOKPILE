"""Strict contracts for the privileged, append-only administration ledger."""

from dataclasses import dataclass
from datetime import UTC, datetime
import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Connection, Engine


OPERATOR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.@-]{0,127}$")
ACTION_RE = re.compile(r"^[a-z][a-z0-9_.-]{2,95}$")
INCIDENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{2,159}$")
EVENT_ID_RE = re.compile(r"^[0-9a-f]{64}$")
RESULTS = frozenset({"attempted", "succeeded", "failed"})
HOST_EVIDENCE_FIELDS = frozenset(
    {
        "action",
        "incident_id",
        "occurred_at",
        "operator",
        "reason",
        "result",
        "result_count",
        "source",
        "target",
        "window_end",
        "window_start",
    }
)


class AdminAuditError(RuntimeError):
    """Raised when privileged audit input or persistence is invalid."""


@dataclass(frozen=True)
class AuditAppend:
    operator_id: str
    action: str
    target_id: str | None
    reason: str
    correlation_id: str
    result: str


def _plain_text(value: Any, *, name: str, minimum: int, maximum: int) -> str:
    if not isinstance(value, str):
        raise AdminAuditError(f"{name} must be text")
    if not minimum <= len(value) <= maximum or any(ord(char) < 32 for char in value):
        raise AdminAuditError(f"{name} is invalid")
    return value


def parse_host_evidence_access(payload: Any) -> AuditAppend:
    """Map D3-L's allowlisted payload without retaining raw client evidence."""

    if not isinstance(payload, dict) or not payload:
        raise AdminAuditError("host evidence audit payload must be an object")
    unexpected = set(payload) - HOST_EVIDENCE_FIELDS
    required = HOST_EVIDENCE_FIELDS - {"result_count"}
    missing = required - set(payload)
    if unexpected or missing:
        raise AdminAuditError("host evidence audit payload fields are invalid")
    serialized = json.dumps(payload, sort_keys=True).lower()
    for forbidden in (
        "client_ip",
        "remote_ip",
        "authorization",
        "cookie",
        "object_key",
        "library_id",
        "user_id",
    ):
        if forbidden in serialized:
            raise AdminAuditError("host evidence audit payload contains a forbidden field")

    operator = _plain_text(payload["operator"], name="operator", minimum=1, maximum=128)
    if OPERATOR_RE.fullmatch(operator) is None:
        raise AdminAuditError("operator is invalid")
    action = _plain_text(payload["action"], name="action", minimum=3, maximum=72)
    if ACTION_RE.fullmatch(action) is None:
        raise AdminAuditError("action is invalid")
    incident = _plain_text(
        payload["incident_id"], name="incident_id", minimum=3, maximum=160
    )
    if INCIDENT_RE.fullmatch(incident) is None:
        raise AdminAuditError("incident_id is invalid")
    reason = _plain_text(payload["reason"], name="reason", minimum=8, maximum=500)
    target = _plain_text(payload["target"], name="target", minimum=1, maximum=160)
    source = payload["source"]
    if source != "d6_defensive_events":
        raise AdminAuditError("host evidence source is invalid")
    result = payload["result"]
    if result not in RESULTS:
        raise AdminAuditError("host evidence result is invalid")
    if "result_count" in payload and (
        isinstance(payload["result_count"], bool)
        or not isinstance(payload["result_count"], int)
        or not 0 <= payload["result_count"] <= 20
    ):
        raise AdminAuditError("result_count is invalid")
    for field in ("occurred_at", "window_start", "window_end"):
        raw = _plain_text(payload[field], name=field, minimum=20, maximum=40)
        try:
            moment = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError as exc:
            raise AdminAuditError(f"{field} is invalid") from exc
        if moment.tzinfo is None:
            raise AdminAuditError(f"{field} must include a timezone")

    return AuditAppend(
        operator_id=operator,
        action=f"host_evidence.{action}",
        target_id=target,
        reason=reason,
        correlation_id=incident,
        result=result,
    )


def append(engine: Engine, entry: AuditAppend) -> dict[str, object]:
    with engine.begin() as connection:
        return append_in_transaction(connection, entry)


def append_in_transaction(connection: Connection, entry: AuditAppend) -> dict[str, object]:
    row = connection.execute(
        text(
            "SELECT sequence_id, event_id, occurred_at, row_hash "
            "FROM admin_audit.append_entry("
            ":operator_id, :action, :target_id, :reason, :correlation_id, :result)"
        ),
        {
            "operator_id": entry.operator_id,
            "action": entry.action,
            "target_id": entry.target_id,
            "reason": entry.reason,
            "correlation_id": entry.correlation_id,
            "result": entry.result,
        },
    ).mappings().one()
    return {
        "event_id": str(row["event_id"]),
        "occurred_at": row["occurred_at"].astimezone(UTC).isoformat(),
        "recorded": True,
        "sequence_id": row["sequence_id"],
        "row_hash": row["row_hash"],
    }


def verify(engine: Engine) -> dict[str, object]:
    with engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT rows_verified, last_sequence_id, last_hash "
                "FROM admin_audit.verify_chain()"
            )
        ).mappings().one()
    return {
        "healthy": True,
        "last_hash": row["last_hash"],
        "last_sequence_id": row["last_sequence_id"],
        "privacy": "aggregate_only",
        "rows_verified": row["rows_verified"],
    }


def prune_expired(engine: Engine) -> dict[str, object]:
    with engine.begin() as connection:
        row = connection.execute(
            text(
                "SELECT rows_deleted, pruned_through_sequence_id, "
                "pruned_through_hash FROM admin_audit.prune_expired()"
            )
        ).mappings().one()
    return {
        "privacy": "aggregate_only",
        "pruned_through_hash": row["pruned_through_hash"],
        "pruned_through_sequence_id": row["pruned_through_sequence_id"],
        "rows_deleted": row["rows_deleted"],
    }
