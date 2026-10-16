from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from bookpile_server.config import Settings
from bookpile_server.models import RateLimitBucket, SecurityEvent
from bookpile_server.repositories.rate_limits import RateLimitRepository
from bookpile_server.services.rate_limits import (
    RateLimitExceededError,
    RateLimitDecisionUnavailableError,
    RateLimiter,
    RateLimitPolicy,
)


class UnavailableRateLimitRepository:
    def __init__(self) -> None:
        self.rolled_back = False

    def consume(self, **_kwargs):
        raise OperationalError("rate-limit probe", {}, RuntimeError("offline"))

    def rollback(self) -> None:
        self.rolled_back = True


def test_rate_limit_uses_hashed_atomic_bucket_and_resets_window(
    session: Session,
) -> None:
    limiter = RateLimiter(RateLimitRepository(session), "test-secret")
    policy = RateLimitPolicy("test_scope", 2, timedelta(minutes=1))
    started_at = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)

    limiter.enforce(
        policy, key="reader@example.com", ip_address="127.0.0.1", now=started_at
    )
    limiter.enforce(
        policy, key="reader@example.com", ip_address="127.0.0.1", now=started_at
    )
    with pytest.raises(RateLimitExceededError) as blocked:
        limiter.enforce(
            policy,
            key="reader@example.com",
            ip_address="127.0.0.1",
            now=started_at,
        )
    assert blocked.value.retry_after == 60

    bucket = session.scalar(select(RateLimitBucket))
    assert bucket is not None
    assert bucket.attempt_count == 3
    assert bucket.key_hash != "reader@example.com"
    assert "reader" not in bucket.key_hash
    events = list(
        session.scalars(
            select(SecurityEvent).where(
                SecurityEvent.event_type == "rate_limit_blocked"
            )
        )
    )
    assert len(events) == 1
    assert events[0].details == {"scope": "test_scope"}

    limiter.enforce(
        policy,
        key="reader@example.com",
        ip_address="127.0.0.1",
        now=started_at + timedelta(minutes=1, seconds=1),
    )
    session.expire_all()
    bucket = session.scalar(select(RateLimitBucket))
    assert bucket is not None
    assert bucket.attempt_count == 1


def test_defensive_modes_are_off_observable_and_privacy_preserving(
    session: Session,
) -> None:
    limiter = RateLimiter(
        RateLimitRepository(session), "test-secret", "git-observation-test"
    )
    policy = RateLimitPolicy("defensive_test", 1, timedelta(minutes=1))
    started_at = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    off = limiter.apply(
        policy,
        key="account@example.com",
        mode="off",
        ip_address="203.0.113.10",
        now=started_at,
    )
    assert off.consumed is False
    assert session.scalar(select(RateLimitBucket)) is None

    limiter.apply(policy, key="account@example.com", mode="observe", now=started_at)
    observed = limiter.apply(
        policy,
        key="account@example.com",
        mode="observe",
        ip_address="203.0.113.10",
        now=started_at,
    )
    assert observed.exceeded is True
    assert observed.retry_after == 60
    event = session.scalar(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "rate_limit_observed"
        )
    )
    assert event is not None
    assert event.ip_address is None
    assert event.details == {
        "scope": "defensive_test",
        "mode": "observe",
        "deployment_revision": "git-observation-test",
    }


def test_defensive_enforcement_does_not_record_raw_ip_by_default(
    session: Session,
) -> None:
    limiter = RateLimiter(RateLimitRepository(session), "test-secret")
    policy = RateLimitPolicy("defensive_enforce", 1, timedelta(minutes=1))
    started_at = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)

    limiter.apply(policy, key="key", mode="enforce", now=started_at)
    with pytest.raises(RateLimitExceededError):
        limiter.apply(
            policy,
            key="key",
            mode="enforce",
            ip_address="203.0.113.10",
            now=started_at,
        )
    event = session.scalar(
        select(SecurityEvent).where(SecurityEvent.event_type == "rate_limit_blocked")
    )
    assert event is not None
    assert event.ip_address is None
    assert event.details == {
        "scope": "defensive_enforce",
        "mode": "enforce",
        "deployment_revision": "development",
    }


def test_login_rate_limit_is_generic_and_supplies_retry_after(
    client, monkeypatch
) -> None:
    from bookpile_server.api.routes import auth

    monkeypatch.setattr(
        auth,
        "LOGIN_IDENTITY",
        RateLimitPolicy("login_identity_test", 2, timedelta(minutes=15)),
    )
    payload = {
        "identifier": "not-a-user",
        "password": "an invalid password",
        "remember_me": False,
    }
    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    assert client.post("/api/v1/auth/login", json=payload).status_code == 401
    blocked = client.post("/api/v1/auth/login", json=payload)
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many requests. Try again later."}
    assert int(blocked.headers["retry-after"]) > 0


def test_production_rejects_development_security_defaults() -> None:
    with pytest.raises(ValueError, match="RATE_LIMIT_KEY_SECRET"):
        Settings(environment="production")

    with pytest.raises(ValueError, match="SESSION_COOKIE_SECURE"):
        Settings(
            environment="production",
            rate_limit_key_secret="a-private-production-secret-with-32-characters",
        )

    settings = Settings(
        environment="production",
        rate_limit_key_secret="a-private-production-secret-with-32-characters",
        session_cookie_secure=True,
        public_base_url="https://bookpile.example",
        database_url="postgresql+psycopg://bookpile:private@db/bookpile",
        deployment_revision="git-1234567",
        api_docs_enabled=False,
        allowed_hosts="bookpile.example",
        trusted_proxy_cidrs="172.18.0.0/16",
        private_object_backend="s3",
        private_object_s3_endpoint_url="https://objects.example",
        private_object_s3_region="eu-test-1",
        private_object_s3_bucket="bookpile-private",
        private_object_s3_access_key_id="test-access-key",
        private_object_s3_secret_access_key="test-secret-key",
        smtp_starttls=True,
        smtp_username="smtp-user",
        smtp_password="smtp-password",
        email_delivery_mode="outbox",
        email_outbox_encryption_secret="private-outbox-secret-with-at-least-32-characters",
    )
    assert settings.session_cookie_secure is True


def test_operation_lease_heartbeat_must_fit_safely_inside_ttl() -> None:
    with pytest.raises(ValueError, match="heartbeat"):
        Settings(
            operation_lease_ttl_seconds=60,
            operation_lease_heartbeat_seconds=31,
        )


def test_database_failure_is_explicit_and_rolls_back() -> None:
    repository = UnavailableRateLimitRepository()
    limiter = RateLimiter(repository, "test-secret")  # type: ignore[arg-type]

    with pytest.raises(RateLimitDecisionUnavailableError):
        limiter.apply(
            RateLimitPolicy("unavailable", 1, timedelta(minutes=1)),
            key="logical-key",
            mode="observe",
        )

    assert repository.rolled_back is True
