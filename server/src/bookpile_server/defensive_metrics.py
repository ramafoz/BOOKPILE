"""Privacy-safe aggregate defensive event metrics."""

from collections import Counter
from datetime import UTC, datetime, timedelta
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import SecurityEvent


AGGREGATED_SECURITY_EVENT_TYPES = frozenset(
    {"operation_lease_blocked", "operation_lease_observed"}
)
SAFE_LABEL = re.compile(r"^[a-z0-9_:-]{1,80}$")
SAFE_REVISION = re.compile(r"^[a-f0-9]{7,64}$")


def aggregate_lease_conflicts(
    session: Session,
    *,
    window: timedelta,
    now: datetime | None = None,
) -> dict[str, object]:
    """Return only bounded labels and counts; never event identity fields."""
    if window <= timedelta(0) or window > timedelta(hours=24):
        raise ValueError("Metric window must be between zero and 24 hours")
    moment = now or datetime.now(UTC)
    events = session.scalars(
        select(SecurityEvent).where(
            SecurityEvent.occurred_at >= moment - window,
            SecurityEvent.event_type.in_(AGGREGATED_SECURITY_EVENT_TYPES),
        )
    )
    counts: Counter[tuple[str, str, str]] = Counter()
    for event in events:
        scope = event.details.get("scope")
        revision = event.details.get("deployment_revision")
        if not isinstance(scope, str) or SAFE_LABEL.fullmatch(scope) is None:
            continue
        if not isinstance(revision, str) or SAFE_REVISION.fullmatch(revision) is None:
            continue
        counts[(event.event_type, scope, revision)] += 1
    groups = [
        {
            "count": count,
            "event_type": event_type,
            "policy": "operation_lease",
            "revision": revision,
            "scope": scope,
        }
        for (event_type, scope, revision), count in sorted(counts.items())
    ]
    return {
        "groups": groups,
        "metric": "lease_conflicts",
        "total": sum(counts.values()),
        "window_seconds": int(window.total_seconds()),
    }
