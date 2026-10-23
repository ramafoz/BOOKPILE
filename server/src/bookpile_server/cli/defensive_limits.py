import argparse
import json
from dataclasses import dataclass
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from ..config import Settings, get_settings
from ..database import SessionFactory
from ..models import OperationLease, RateLimitBucket, SecurityEvent
from ..repositories.rate_limits import RateLimitRepository
from ..services.costly_operation_limits import CostlyOperationLimiter
from ..services.mutation_limits import MutationRateLimiter
from ..services.rate_limits import RateLimitExceededError, RateLimiter
from ..services.specific_operation_limits import SpecificOperationRateLimiter


COSTLY_SCOPES = (
    "import_preflight_user",
    "import_preflight_library",
    "import_consolidation_user",
    "import_consolidation_library",
    "portable_export_user",
    "portable_export_library",
)
MUTATION_SCOPES = ("mutation_user", "mutation_library")
SPECIFIC_OPERATION_SCOPES = (
    "bibliographic_lookup",
    "bibliographic_lookup_ip",
    "bibliographic_lookup_library",
    "cover_upload",
    "cover_upload_library",
    "rearrangement_user",
    "rearrangement_library",
)
STATUS_SCOPES = (
    *COSTLY_SCOPES,
    *MUTATION_SCOPES,
    *SPECIFIC_OPERATION_SCOPES,
    "general_api_ip",
)
REHEARSAL_CONFIRMATION = "STAGING-LIMIT-REHEARSAL"
MUTATION_REHEARSAL_CONFIRMATION = "STAGING-MUTATION-LIMIT-REHEARSAL"
SPECIFIC_REHEARSAL_CONFIRMATION = "STAGING-SPECIFIC-LIMIT-REHEARSAL"


@dataclass(frozen=True)
class RehearsalOperation:
    name: str
    user_attempts: int
    library_attempts: int
    check: Callable[..., None]


def _operations(
    limiter: CostlyOperationLimiter, settings: Settings
) -> tuple[RehearsalOperation, ...]:
    return (
        RehearsalOperation(
            "import_preflight",
            settings.import_attempts_per_user_per_hour,
            settings.import_attempts_per_library_per_hour,
            limiter.check_import_preflight,
        ),
        RehearsalOperation(
            "import_consolidation",
            settings.import_attempts_per_user_per_hour,
            settings.import_attempts_per_library_per_hour,
            limiter.check_import_consolidation,
        ),
        RehearsalOperation(
            "portable_export",
            settings.export_attempts_per_user_per_hour,
            settings.export_attempts_per_library_per_hour,
            limiter.check_export,
        ),
    )


def _exercise(
    check: Callable[..., None],
    attempts: int,
    identities: Callable[[int], tuple[UUID, UUID]],
    mode: str,
) -> int:
    blocked = 0
    for index in range(attempts + 1):
        user_id, library_id = identities(index)
        try:
            check(user_id=user_id, library_id=library_id)
        except RateLimitExceededError:
            blocked += 1
    expected = 1 if mode == "enforce" else 0
    if blocked != expected:
        raise RuntimeError(
            f"Unexpected blocked decision count: expected {expected}, found {blocked}."
        )
    return blocked


def rehearse_costly_limits(
    session: Session, settings: Settings, *, confirmation: str
) -> dict[str, object]:
    if settings.environment != "staging":
        raise RuntimeError("The costly-limit rehearsal is restricted to staging.")
    if settings.defensive_limit_mode not in {"observe", "enforce"}:
        raise RuntimeError(
            "The costly-limit rehearsal requires observe or enforce mode."
        )
    if confirmation != REHEARSAL_CONFIRMATION:
        raise RuntimeError(
            f"Pass --confirm {REHEARSAL_CONFIRMATION} to create synthetic evidence."
        )

    limiter = CostlyOperationLimiter(
        RateLimiter(
            RateLimitRepository(session),
            settings.rate_limit_key_secret,
            settings.deployment_revision,
        ),
        settings,
    )
    previous_event_id = session.scalar(select(func.max(SecurityEvent.id))) or 0
    run_id = uuid4()
    results: list[dict[str, object]] = []
    for operation in _operations(limiter, settings):
        shared_user = uuid4()
        user_blocked = _exercise(
            operation.check,
            operation.user_attempts,
            lambda _index, user_id=shared_user: (user_id, uuid4()),
            settings.defensive_limit_mode,
        )
        shared_library = uuid4()
        library_blocked = _exercise(
            operation.check,
            operation.library_attempts,
            lambda _index, library_id=shared_library: (uuid4(), library_id),
            settings.defensive_limit_mode,
        )
        results.append(
            {
                "operation": operation.name,
                "user_attempts": operation.user_attempts + 1,
                "library_attempts": operation.library_attempts + 1,
                "blocked_decisions": user_blocked + library_blocked,
            }
        )

    event_type = (
        "rate_limit_blocked"
        if settings.defensive_limit_mode == "enforce"
        else "rate_limit_observed"
    )
    observed_scopes = sorted(
        {
            event.details.get("scope")
            for event in session.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.id > previous_event_id,
                    SecurityEvent.event_type == event_type,
                )
            )
            if event.details.get("deployment_revision")
            == settings.deployment_revision
            and event.details.get("scope") in COSTLY_SCOPES
        }
    )
    missing = sorted(set(COSTLY_SCOPES) - set(observed_scopes))
    if missing:
        raise RuntimeError(
            "The rehearsal did not produce evidence for: " + ", ".join(missing)
        )
    return {
        "environment": settings.environment,
        "mode": settings.defensive_limit_mode,
        "deployment_revision": settings.deployment_revision,
        "rehearsal_id": str(run_id),
        "synthetic_only": True,
        "event_type": event_type,
        "observed_scopes": observed_scopes,
        "operations": results,
    }


def _exercise_mutation(
    check: Callable[..., None],
    threshold: int,
    mode: str,
    correlation_id: str,
) -> int:
    identity = uuid4()
    blocked = 0
    for _index in range(threshold + 1):
        try:
            check(identity, correlation_id=correlation_id)
        except RateLimitExceededError:
            blocked += 1
    expected = 1 if mode == "enforce" else 0
    if blocked != expected:
        raise RuntimeError(
            f"Unexpected blocked decision count: expected {expected}, found {blocked}."
        )
    return blocked


def rehearse_mutation_limits(
    session: Session, settings: Settings, *, confirmation: str
) -> dict[str, object]:
    if settings.environment != "staging":
        raise RuntimeError("The mutation-limit rehearsal is restricted to staging.")
    modes = {
        "mutation_user": settings.mutation_user_limit_mode,
        "mutation_library": settings.mutation_library_limit_mode,
    }
    if any(mode not in {"observe", "enforce"} for mode in modes.values()):
        raise RuntimeError(
            "The mutation-limit rehearsal requires both policies in observe or "
            "enforce mode."
        )
    if confirmation != MUTATION_REHEARSAL_CONFIRMATION:
        raise RuntimeError(
            "Pass --confirm "
            f"{MUTATION_REHEARSAL_CONFIRMATION} to create synthetic evidence."
        )

    limiter = MutationRateLimiter(
        RateLimiter(
            RateLimitRepository(session),
            settings.rate_limit_key_secret,
            settings.deployment_revision,
        ),
        settings,
    )
    run_id = str(uuid4())
    previous_event_id = session.scalar(select(func.max(SecurityEvent.id))) or 0
    scenarios = (
        (
            "mutation_user",
            settings.mutation_attempts_per_user_per_15_minutes,
            settings.mutation_user_limit_mode,
            limiter.check_user,
        ),
        (
            "mutation_library",
            settings.mutation_attempts_per_library_per_15_minutes,
            settings.mutation_library_limit_mode,
            limiter.check_library,
        ),
    )
    results = []
    for scope, threshold, mode, check in scenarios:
        blocked = _exercise_mutation(check, threshold, mode, run_id)
        expected_event = (
            "rate_limit_blocked" if mode == "enforce" else "rate_limit_observed"
        )
        matching_events = list(
            session.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.id > previous_event_id,
                    SecurityEvent.event_type == expected_event,
                    SecurityEvent.details["scope"].as_string() == scope,
                    SecurityEvent.details["deployment_revision"].as_string()
                    == settings.deployment_revision,
                    SecurityEvent.details["correlation_id"].as_string() == run_id,
                )
            )
        )
        if len(matching_events) != 1:
            raise RuntimeError(
                f"Expected one {expected_event} event for {scope}, "
                f"found {len(matching_events)}."
            )
        results.append(
            {
                "scope": scope,
                "mode": mode,
                "attempts": threshold + 1,
                "blocked_decisions": blocked,
                "event_type": expected_event,
            }
        )

    return {
        "environment": settings.environment,
        "deployment_revision": settings.deployment_revision,
        "rehearsal_id": run_id,
        "synthetic_only": True,
        "operations": results,
    }


def rehearse_specific_operation_limits(
    session: Session, settings: Settings, *, confirmation: str
) -> dict[str, object]:
    if settings.environment != "staging":
        raise RuntimeError(
            "The specific-operation rehearsal is restricted to staging."
        )
    modes = {
        "bibliographic_lookup_ip": settings.bibliographic_lookup_limit_mode,
        "bibliographic_lookup_library": settings.bibliographic_lookup_limit_mode,
        "cover_upload_library": settings.cover_upload_library_limit_mode,
        "rearrangement_user": settings.rearrangement_limit_mode,
        "rearrangement_library": settings.rearrangement_limit_mode,
    }
    if any(mode not in {"observe", "enforce"} for mode in modes.values()):
        raise RuntimeError(
            "The specific-operation rehearsal requires every new policy in "
            "observe or enforce mode."
        )
    if confirmation != SPECIFIC_REHEARSAL_CONFIRMATION:
        raise RuntimeError(
            "Pass --confirm "
            f"{SPECIFIC_REHEARSAL_CONFIRMATION} to create synthetic evidence."
        )

    limiter = SpecificOperationRateLimiter(
        RateLimiter(
            RateLimitRepository(session),
            settings.rate_limit_key_secret,
            settings.deployment_revision,
        ),
        settings,
    )
    run_id = str(uuid4())
    previous_event_id = session.scalar(select(func.max(SecurityEvent.id))) or 0
    scenarios = (
        (
            "bibliographic_lookup_ip",
            settings.bibliographic_lookup_attempts_per_ip_per_hour,
            settings.bibliographic_lookup_limit_mode,
            limiter.check_bibliographic_ip,
        ),
        (
            "bibliographic_lookup_library",
            settings.bibliographic_lookup_attempts_per_library_per_hour,
            settings.bibliographic_lookup_limit_mode,
            limiter.check_bibliographic_library,
        ),
        (
            "cover_upload_library",
            settings.cover_upload_attempts_per_library_per_hour,
            settings.cover_upload_library_limit_mode,
            limiter.check_cover_library,
        ),
        (
            "rearrangement_user",
            settings.rearrangement_attempts_per_user_per_minute,
            settings.rearrangement_limit_mode,
            limiter.check_rearrangement_user,
        ),
        (
            "rearrangement_library",
            settings.rearrangement_attempts_per_library_per_minute,
            settings.rearrangement_limit_mode,
            limiter.check_rearrangement_library,
        ),
    )
    results = []
    for scope, threshold, mode, check in scenarios:
        identity = str(uuid4()) if scope.endswith("_ip") else uuid4()
        blocked = 0
        for _index in range(threshold + 1):
            try:
                check(identity, correlation_id=run_id)
            except RateLimitExceededError:
                blocked += 1
        expected_blocked = 1 if mode == "enforce" else 0
        if blocked != expected_blocked:
            raise RuntimeError(
                f"Unexpected blocked decision count for {scope}: expected "
                f"{expected_blocked}, found {blocked}."
            )
        expected_event = (
            "rate_limit_blocked" if mode == "enforce" else "rate_limit_observed"
        )
        matching_events = list(
            session.scalars(
                select(SecurityEvent).where(
                    SecurityEvent.id > previous_event_id,
                    SecurityEvent.event_type == expected_event,
                    SecurityEvent.details["scope"].as_string() == scope,
                    SecurityEvent.details["deployment_revision"].as_string()
                    == settings.deployment_revision,
                    SecurityEvent.details["correlation_id"].as_string() == run_id,
                )
            )
        )
        if len(matching_events) != 1:
            raise RuntimeError(
                f"Expected one {expected_event} event for {scope}, "
                f"found {len(matching_events)}."
            )
        results.append(
            {
                "scope": scope,
                "mode": mode,
                "attempts": threshold + 1,
                "blocked_decisions": blocked,
                "event_type": expected_event,
            }
        )

    return {
        "environment": settings.environment,
        "deployment_revision": settings.deployment_revision,
        "rehearsal_id": run_id,
        "synthetic_only": True,
        "operations": results,
    }


def costly_limit_status(session: Session, settings: Settings) -> dict[str, object]:
    bucket_rows = session.execute(
        select(
            RateLimitBucket.scope,
            func.count().label("buckets"),
            func.sum(RateLimitBucket.attempt_count).label("attempts"),
            func.max(RateLimitBucket.attempt_count).label("highest_bucket"),
            func.min(RateLimitBucket.window_started_at).label("first_window"),
            func.max(RateLimitBucket.updated_at).label("last_activity"),
        )
        .where(RateLimitBucket.scope.in_(STATUS_SCOPES))
        .group_by(RateLimitBucket.scope)
        .order_by(RateLimitBucket.scope)
    ).all()
    relevant_events = []
    for event in session.scalars(
        select(SecurityEvent)
        .where(
            SecurityEvent.event_type.in_(
                (
                    "rate_limit_observed",
                    "rate_limit_blocked",
                    "operation_lease_observed",
                    "operation_lease_blocked",
                )
            ),
            SecurityEvent.details["scope"].as_string().in_(STATUS_SCOPES),
        )
        .order_by(SecurityEvent.occurred_at.desc())
        .limit(100)
    ):
        scope = event.details.get("scope")
        relevant_events.append(
            {
                "occurred_at": event.occurred_at.isoformat(),
                "event_type": event.event_type,
                "scope": scope,
                "mode": event.details.get("mode"),
                "deployment_revision": event.details.get("deployment_revision"),
                "correlation_id": event.details.get("correlation_id"),
            }
        )
    lease_rows = session.execute(
        select(
            OperationLease.scope,
            func.count().label("leases"),
            func.sum(
                case(
                    (
                        OperationLease.released_at.is_(None)
                        & (OperationLease.expires_at > func.now()),
                        1,
                    ),
                    else_=0,
                )
            ).label("active"),
            func.max(OperationLease.fencing_token).label("highest_fencing_token"),
            func.max(OperationLease.renewed_at).label("last_renewal"),
        )
        .where(
            OperationLease.scope.in_(
                (
                    "import_consolidation_user",
                    "import_consolidation_library",
                    "portable_export_user",
                    "portable_export_library",
                )
            )
        )
        .group_by(OperationLease.scope)
        .order_by(OperationLease.scope)
    ).all()
    return {
        "environment": settings.environment,
        "mode": settings.defensive_limit_mode,
        "general_api_mode": settings.general_api_limit_mode,
        "mutation_user_mode": settings.mutation_user_limit_mode,
        "mutation_library_mode": settings.mutation_library_limit_mode,
        "bibliographic_lookup_mode": settings.bibliographic_lookup_limit_mode,
        "cover_upload_library_mode": settings.cover_upload_library_limit_mode,
        "rearrangement_mode": settings.rearrangement_limit_mode,
        "deployment_revision": settings.deployment_revision,
        "thresholds": {
            "general_api_ip_per_minute": (
                settings.general_api_attempts_per_ip_per_minute
            ),
            "mutation_user_per_15_minutes": (
                settings.mutation_attempts_per_user_per_15_minutes
            ),
            "mutation_library_per_15_minutes": (
                settings.mutation_attempts_per_library_per_15_minutes
            ),
            "bibliographic_lookup_user_per_hour": (
                settings.bibliographic_lookup_attempts_per_user_per_hour
            ),
            "bibliographic_lookup_ip_per_hour": (
                settings.bibliographic_lookup_attempts_per_ip_per_hour
            ),
            "bibliographic_lookup_library_per_hour": (
                settings.bibliographic_lookup_attempts_per_library_per_hour
            ),
            "cover_upload_user_per_hour": settings.cover_upload_attempts_per_hour,
            "cover_upload_library_per_hour": (
                settings.cover_upload_attempts_per_library_per_hour
            ),
            "rearrangement_user_per_minute": (
                settings.rearrangement_attempts_per_user_per_minute
            ),
            "rearrangement_library_per_minute": (
                settings.rearrangement_attempts_per_library_per_minute
            ),
            "import_user_per_hour": settings.import_attempts_per_user_per_hour,
            "import_library_per_hour": settings.import_attempts_per_library_per_hour,
            "export_user_per_hour": settings.export_attempts_per_user_per_hour,
            "export_library_per_hour": settings.export_attempts_per_library_per_hour,
        },
        "buckets": [
            {
                "scope": row.scope,
                "buckets": row.buckets,
                "attempts": row.attempts,
                "highest_bucket": row.highest_bucket,
                "first_window": row.first_window.isoformat(),
                "last_activity": row.last_activity.isoformat(),
            }
            for row in bucket_rows
        ],
        "events": relevant_events,
        "leases": [
            {
                "scope": row.scope,
                "leases": row.leases,
                "active": row.active or 0,
                "highest_fencing_token": row.highest_fencing_token,
                "last_renewal": row.last_renewal.isoformat(),
            }
            for row in lease_rows
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("status")
    rehearsal = subparsers.add_parser("rehearse")
    rehearsal.add_argument("--confirm", required=True)
    mutation_rehearsal = subparsers.add_parser("rehearse-mutations")
    mutation_rehearsal.add_argument("--confirm", required=True)
    specific_rehearsal = subparsers.add_parser("rehearse-specific")
    specific_rehearsal.add_argument("--confirm", required=True)
    args = parser.parse_args()
    settings = get_settings()
    with SessionFactory() as session:
        if args.command == "status":
            payload = costly_limit_status(session, settings)
        elif args.command == "rehearse":
            payload = rehearse_costly_limits(
                session, settings, confirmation=args.confirm
            )
        elif args.command == "rehearse-mutations":
            payload = rehearse_mutation_limits(
                session, settings, confirmation=args.confirm
            )
        else:
            payload = rehearse_specific_operation_limits(
                session, settings, confirmation=args.confirm
            )
    print(json.dumps(payload, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
