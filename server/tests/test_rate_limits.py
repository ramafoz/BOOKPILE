from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.config import Settings
from bookpile_server.models import RateLimitBucket, SecurityEvent
from bookpile_server.repositories.rate_limits import RateLimitRepository
from bookpile_server.services.rate_limits import (
    RateLimitExceededError,
    RateLimiter,
    RateLimitPolicy,
)


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
            rate_limit_key_secret="a-private-production-secret",
        )

    settings = Settings(
        environment="production",
        rate_limit_key_secret="a-private-production-secret",
        session_cookie_secure=True,
        public_base_url="https://bookpile.example",
    )
    assert settings.session_cookie_secure is True
