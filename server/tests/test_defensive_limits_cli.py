from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.cli.defensive_limits import (
    COSTLY_SCOPES,
    MUTATION_REHEARSAL_CONFIRMATION,
    REHEARSAL_CONFIRMATION,
    costly_limit_status,
    rehearse_costly_limits,
    rehearse_mutation_limits,
)
from bookpile_server.config import Settings
from bookpile_server.models import Library, RateLimitBucket, SecurityEvent, User
from bookpile_server.services.rate_limits import RateLimiter


def settings(mode: str, *, environment: str = "staging") -> Settings:
    selected = Settings(
        environment="test",
        defensive_limit_mode=mode,
        import_attempts_per_user_per_hour=2,
        import_attempts_per_library_per_hour=3,
        export_attempts_per_user_per_hour=2,
        export_attempts_per_library_per_hour=3,
        deployment_revision=f"git-rehearsal-{uuid4()}",
        rate_limit_key_secret=f"rehearsal-secret-{uuid4()}",
    )
    return selected.model_copy(update={"environment": environment})


@pytest.mark.parametrize(
    ("mode", "event_type", "blocked"),
    (
        ("observe", "rate_limit_observed", 0),
        ("enforce", "rate_limit_blocked", 2),
    ),
)
def test_rehearsal_exercises_every_costly_scope(
    session: Session, mode: str, event_type: str, blocked: int
) -> None:
    selected = settings(mode)

    result = rehearse_costly_limits(
        session, selected, confirmation=REHEARSAL_CONFIRMATION
    )

    assert result["synthetic_only"] is True
    assert result["observed_scopes"] == sorted(COSTLY_SCOPES)
    assert all(
        item["blocked_decisions"] == blocked for item in result["operations"]
    )
    events = list(
        session.scalars(
            select(SecurityEvent).where(SecurityEvent.event_type == event_type)
        )
    )
    assert {event.details["scope"] for event in events} == set(COSTLY_SCOPES)
    assert all(event.ip_address is None for event in events)

    status = costly_limit_status(session, selected)
    assert status["mode"] == mode
    assert {item["scope"] for item in status["buckets"]} == set(COSTLY_SCOPES)
    assert {item["scope"] for item in status["events"]} == set(COSTLY_SCOPES)


@pytest.mark.parametrize(
    "selected",
    (
        settings("off"),
        settings("observe", environment="production"),
    ),
)
def test_rehearsal_refuses_unsafe_environment_or_mode(
    session: Session, selected: Settings
) -> None:
    with pytest.raises(RuntimeError):
        rehearse_costly_limits(
            session, selected, confirmation=REHEARSAL_CONFIRMATION
        )

    assert list(session.scalars(select(RateLimitBucket))) == []


def test_rehearsal_requires_explicit_confirmation(session: Session) -> None:
    with pytest.raises(RuntimeError, match="--confirm"):
        rehearse_costly_limits(session, settings("observe"), confirmation="no")

    assert list(session.scalars(select(RateLimitBucket))) == []


def test_status_filters_events_before_limiting_results(session: Session) -> None:
    selected = settings("observe")
    started_at = datetime.now(UTC) - timedelta(minutes=5)
    session.add(
        SecurityEvent(
            occurred_at=started_at,
            event_type="rate_limit_observed",
            details={
                "scope": "portable_export_user",
                "mode": "observe",
                "deployment_revision": selected.deployment_revision,
            },
        )
    )
    session.add_all(
        SecurityEvent(
            occurred_at=started_at + timedelta(seconds=index + 1),
            event_type="rate_limit_blocked",
            details={"scope": "login_ip"},
        )
        for index in range(101)
    )
    session.commit()

    status = costly_limit_status(session, selected)

    assert [event["scope"] for event in status["events"]] == [
        "portable_export_user"
    ]


def test_status_includes_general_api_limit_evidence(session: Session) -> None:
    selected = settings("observe").model_copy(
        update={"general_api_attempts_per_ip_per_minute": 600}
    )
    session.add(
        RateLimitBucket(
            scope="general_api_ip",
            key_hash="synthetic-hash",
            attempt_count=601,
            window_started_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    session.add(
        SecurityEvent(
            event_type="rate_limit_observed",
            details={
                "scope": "general_api_ip",
                "mode": "observe",
                "deployment_revision": selected.deployment_revision,
            },
        )
    )
    session.commit()

    status = costly_limit_status(session, selected)

    assert status["thresholds"]["general_api_ip_per_minute"] == 600
    assert status["general_api_mode"] == "off"
    assert status["buckets"][0]["scope"] == "general_api_ip"
    assert status["events"][0]["scope"] == "general_api_ip"


def test_status_includes_mutation_limit_configuration(session: Session) -> None:
    selected = settings("observe").model_copy(
        update={
            "mutation_user_limit_mode": "observe",
            "mutation_library_limit_mode": "enforce",
            "mutation_attempts_per_user_per_15_minutes": 240,
            "mutation_attempts_per_library_per_15_minutes": 600,
        }
    )
    session.add_all(
        (
            RateLimitBucket(
                scope="mutation_user",
                key_hash="synthetic-user-hash",
                attempt_count=241,
                window_started_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
            RateLimitBucket(
                scope="mutation_library",
                key_hash="synthetic-library-hash",
                attempt_count=601,
                window_started_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            ),
        )
    )
    session.commit()

    status = costly_limit_status(session, selected)

    assert status["mutation_user_mode"] == "observe"
    assert status["mutation_library_mode"] == "enforce"
    assert status["thresholds"]["mutation_user_per_15_minutes"] == 240
    assert status["thresholds"]["mutation_library_per_15_minutes"] == 600
    assert [item["scope"] for item in status["buckets"]] == [
        "mutation_library",
        "mutation_user",
    ]


@pytest.mark.parametrize(
    ("user_mode", "library_mode", "event_types", "blocked"),
    (
        ("observe", "observe", {"rate_limit_observed"}, [0, 0]),
        ("enforce", "enforce", {"rate_limit_blocked"}, [1, 1]),
        (
            "observe",
            "enforce",
            {"rate_limit_observed", "rate_limit_blocked"},
            [0, 1],
        ),
    ),
)
def test_mutation_rehearsal_uses_only_synthetic_keys_and_verifies_evidence(
    session: Session,
    user_mode: str,
    library_mode: str,
    event_types: set[str],
    blocked: list[int],
) -> None:
    selected = settings("observe").model_copy(
        update={
            "mutation_user_limit_mode": user_mode,
            "mutation_library_limit_mode": library_mode,
            "mutation_attempts_per_user_per_15_minutes": 2,
            "mutation_attempts_per_library_per_15_minutes": 3,
        }
    )

    result = rehearse_mutation_limits(
        session,
        selected,
        confirmation=MUTATION_REHEARSAL_CONFIRMATION,
    )

    assert result["synthetic_only"] is True
    assert [item["scope"] for item in result["operations"]] == [
        "mutation_user",
        "mutation_library",
    ]
    assert [item["attempts"] for item in result["operations"]] == [3, 4]
    assert [item["blocked_decisions"] for item in result["operations"]] == blocked
    assert {item["event_type"] for item in result["operations"]} == event_types
    assert {
        event.event_type for event in session.scalars(select(SecurityEvent))
    } == event_types
    assert {
        event.details.get("correlation_id")
        for event in session.scalars(select(SecurityEvent))
    } == {result["rehearsal_id"]}
    stored_buckets = list(session.scalars(select(RateLimitBucket)))
    assert {bucket.scope for bucket in stored_buckets} == {
        "mutation_user",
        "mutation_library",
    }
    assert all(len(bucket.key_hash) == 64 for bucket in stored_buckets)
    assert list(session.scalars(select(User))) == []
    assert list(session.scalars(select(Library))) == []


def test_mutation_rehearsal_ignores_uncorrelated_concurrent_evidence(
    monkeypatch, session: Session
) -> None:
    selected = settings("observe").model_copy(
        update={
            "mutation_user_limit_mode": "observe",
            "mutation_library_limit_mode": "observe",
            "mutation_attempts_per_user_per_15_minutes": 1,
            "mutation_attempts_per_library_per_15_minutes": 1,
        }
    )
    original_apply = RateLimiter.apply
    injected = False

    def apply_with_noise(self, policy, **kwargs):
        nonlocal injected
        if not injected:
            injected = True
            session.add(
                SecurityEvent(
                    event_type="rate_limit_observed",
                    details={
                        "scope": "mutation_user",
                        "mode": "observe",
                        "deployment_revision": selected.deployment_revision,
                    },
                )
            )
            session.commit()
        return original_apply(self, policy, **kwargs)

    monkeypatch.setattr(RateLimiter, "apply", apply_with_noise)

    result = rehearse_mutation_limits(
        session,
        selected,
        confirmation=MUTATION_REHEARSAL_CONFIRMATION,
    )

    assert [item["event_type"] for item in result["operations"]] == [
        "rate_limit_observed",
        "rate_limit_observed",
    ]
    events = list(session.scalars(select(SecurityEvent)))
    assert len(events) == 3
    assert sum(
        event.details.get("correlation_id") == result["rehearsal_id"]
        for event in events
    ) == 2


@pytest.mark.parametrize(
    "selected",
    (
        settings("observe").model_copy(
            update={
                "mutation_user_limit_mode": "off",
                "mutation_library_limit_mode": "observe",
            }
        ),
        settings("observe").model_copy(
            update={
                "environment": "production",
                "mutation_user_limit_mode": "observe",
                "mutation_library_limit_mode": "observe",
            }
        ),
    ),
)
def test_mutation_rehearsal_refuses_unsafe_environment_or_mode(
    session: Session, selected: Settings
) -> None:
    with pytest.raises(RuntimeError):
        rehearse_mutation_limits(
            session,
            selected,
            confirmation=MUTATION_REHEARSAL_CONFIRMATION,
        )

    assert list(session.scalars(select(RateLimitBucket))) == []


def test_mutation_rehearsal_requires_explicit_confirmation(
    session: Session,
) -> None:
    selected = settings("observe").model_copy(
        update={
            "mutation_user_limit_mode": "observe",
            "mutation_library_limit_mode": "observe",
        }
    )
    with pytest.raises(RuntimeError, match="--confirm"):
        rehearse_mutation_limits(session, selected, confirmation="no")

    assert list(session.scalars(select(RateLimitBucket))) == []
