from uuid import uuid4
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import Settings
from bookpile_server.models import RateLimitBucket, SecurityEvent
from bookpile_server.repositories.rate_limits import RateLimitRepository
from bookpile_server.services.costly_operation_limits import CostlyOperationLimiter
from bookpile_server.services.rate_limits import RateLimitExceededError, RateLimiter
from bookpile_server.services.rate_limits import RateLimitDecisionUnavailableError
from bookpile_server.api.routes.imports import apply_import_limit
from bookpile_server.api.routes.exports import download_portable_export
from bookpile_server.services.portable_exports import PortableExportNotFound


def costly_limiter(session: Session, mode: str) -> CostlyOperationLimiter:
    settings = Settings(
        defensive_limit_mode=mode,
        import_attempts_per_user_per_hour=1,
        import_attempts_per_library_per_hour=1,
        export_attempts_per_user_per_hour=1,
        export_attempts_per_library_per_hour=1,
    )
    return CostlyOperationLimiter(
        RateLimiter(
            RateLimitRepository(session),
            "costly-operation-test-secret",
            "git-costly-test",
        ),
        settings,
    )


def test_off_mode_does_not_create_costly_operation_buckets(session: Session) -> None:
    limiter = costly_limiter(session, "off")

    limiter.check_import_preflight(user_id=uuid4(), library_id=uuid4())

    assert list(session.scalars(select(RateLimitBucket))) == []


def test_observe_mode_records_threshold_crossings_without_blocking(
    session: Session,
) -> None:
    limiter = costly_limiter(session, "observe")
    user_id = uuid4()
    library_id = uuid4()

    limiter.check_import_preflight(user_id=user_id, library_id=library_id)
    limiter.check_import_preflight(user_id=user_id, library_id=library_id)

    buckets = list(session.scalars(select(RateLimitBucket)))
    assert len(buckets) == 2
    assert {bucket.attempt_count for bucket in buckets} == {2}
    events = list(
        session.scalars(
            select(SecurityEvent).where(
                SecurityEvent.event_type == "rate_limit_observed"
            )
        )
    )
    assert {event.details["scope"] for event in events} == {
        "import_preflight_user",
        "import_preflight_library",
    }
    assert all(event.ip_address is None for event in events)
    assert all(
        event.details["deployment_revision"] == "git-costly-test"
        for event in events
    )


def test_enforce_mode_rejects_repeated_costly_operation(session: Session) -> None:
    limiter = costly_limiter(session, "enforce")
    user_id = uuid4()
    library_id = uuid4()

    limiter.check_export(user_id=user_id, library_id=library_id)
    with pytest.raises(RateLimitExceededError) as blocked:
        limiter.check_export(user_id=user_id, library_id=library_id)

    assert blocked.value.retry_after > 0


class UnavailableCostlyLimiter:
    def check_import_preflight(self, **_kwargs) -> None:
        raise RateLimitDecisionUnavailableError


def test_import_route_returns_503_when_limit_decision_is_unavailable() -> None:
    with pytest.raises(HTTPException) as unavailable:
        apply_import_limit(
            UnavailableCostlyLimiter(),  # type: ignore[arg-type]
            phase="preflight",
            user_id=uuid4(),
            library_id=uuid4(),
        )

    assert unavailable.value.status_code == 503
    assert unavailable.value.detail == "Request limiting is temporarily unavailable."


class MissingExportService:
    def require_owner(self, **_kwargs) -> None:
        raise PortableExportNotFound


class RecordingExportLimiter:
    called = False

    def check_export(self, **_kwargs) -> None:
        self.called = True


class UnexpectedExportLeases:
    def acquire_export(self, **_kwargs):
        raise AssertionError("leases must follow library authorization")


def test_export_authorization_precedes_library_limit_consumption() -> None:
    limiter = RecordingExportLimiter()

    with pytest.raises(HTTPException) as missing:
        download_portable_export(
            library_id=uuid4(),
            service=MissingExportService(),  # type: ignore[arg-type]
            limiter=limiter,  # type: ignore[arg-type]
            leases=UnexpectedExportLeases(),  # type: ignore[arg-type]
            context=SimpleNamespace(user_id=uuid4()),  # type: ignore[arg-type]
        )

    assert missing.value.status_code == 404
    assert limiter.called is False
