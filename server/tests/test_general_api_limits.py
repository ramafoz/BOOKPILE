import json
import logging
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bookpile_server import main
from bookpile_server.config import Settings
from bookpile_server.general_api_limits import GeneralApiRateLimitMiddleware
from bookpile_server.models import RateLimitBucket, SecurityEvent
from bookpile_server.services.rate_limits import RateLimitDecisionUnavailableError


def limit_settings(mode: str, *, attempts: int = 2) -> Settings:
    selected = Settings(
        environment="test",
        deployment_revision=f"git-general-limit-{uuid4()}",
        rate_limit_key_secret=f"general-limit-secret-{uuid4()}",
        general_api_limit_mode=mode,
    )
    return selected.model_copy(
        update={"general_api_attempts_per_ip_per_minute": attempts}
    )


def limited_client(
    monkeypatch,
    session: Session,
    settings: Settings,
    *,
    client_ip: str = "198.51.100.24",
) -> TestClient:
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    return TestClient(
        main.create_app(rate_limit_session_factory=factory),
        client=(client_ip, 12345),
    )


def test_general_api_observe_records_excess_without_blocking(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("observe")
    with limited_client(monkeypatch, session, settings) as client:
        responses = [client.get("/api/v1/not-a-route") for _ in range(3)]

    assert [response.status_code for response in responses] == [404, 404, 404]
    session.expire_all()
    bucket = session.scalar(
        select(RateLimitBucket).where(RateLimitBucket.scope == "general_api_ip")
    )
    assert bucket is not None
    assert bucket.attempt_count == 3
    assert "198.51.100.24" not in bucket.key_hash
    event = session.scalar(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "rate_limit_observed"
        )
    )
    assert event is not None
    assert event.ip_address is None
    assert event.details == {
        "scope": "general_api_ip",
        "mode": "observe",
        "deployment_revision": settings.deployment_revision,
    }


def test_general_api_enforce_returns_generic_429_with_request_metadata(
    monkeypatch, session: Session, caplog
) -> None:
    settings = limit_settings("enforce")
    with caplog.at_level(logging.INFO, logger="bookpile.requests"):
        with limited_client(monkeypatch, session, settings) as client:
            first = client.get("/api/v1/not-a-route")
            second = client.get("/api/v1/not-a-route")
            blocked = client.get("/api/v1/not-a-route")

    assert first.status_code == second.status_code == 404
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "Too many requests. Try again later."}
    assert int(blocked.headers["retry-after"]) > 0
    assert blocked.headers["cache-control"] == "no-store"
    assert blocked.headers["x-request-id"]
    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "bookpile.requests"
    ]
    assert payloads[-1]["status"] == 429
    assert payloads[-1]["outcome_class"] == "rate_limited"


def test_general_api_limit_excludes_health_and_non_api_paths(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("enforce", attempts=1)
    with limited_client(monkeypatch, session, settings) as client:
        assert all(client.get("/health/live").status_code == 200 for _ in range(3))
        assert all(client.get("/").status_code == 404 for _ in range(3))

    assert session.scalar(select(RateLimitBucket)) is None


def test_general_api_limit_uses_canonical_client_address(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("enforce", attempts=1)
    with limited_client(
        monkeypatch,
        session,
        settings,
        client_ip="2001:0db8:0000:0000:0000:0000:0000:0001",
    ) as expanded:
        assert expanded.get("/api/v1/not-a-route").status_code == 404
    with limited_client(
        monkeypatch,
        session,
        settings,
        client_ip="2001:db8::1",
    ) as compressed:
        response = compressed.get("/api/v1/not-a-route")

    assert response.status_code == 429
    assert session.scalar(
        select(RateLimitBucket).where(RateLimitBucket.scope == "general_api_ip")
    ).attempt_count == 2


def test_general_api_limit_treats_ipv4_mapped_address_as_ipv4(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("enforce", attempts=1)
    with limited_client(
        monkeypatch, session, settings, client_ip="::ffff:198.51.100.24"
    ) as mapped:
        assert mapped.get("/api/v1/not-a-route").status_code == 404
    with limited_client(
        monkeypatch, session, settings, client_ip="198.51.100.24"
    ) as ipv4:
        response = ipv4.get("/api/v1/not-a-route")

    assert response.status_code == 429
    assert session.scalar(
        select(RateLimitBucket).where(RateLimitBucket.scope == "general_api_ip")
    ).attempt_count == 2


def test_general_api_limit_off_does_not_create_a_bucket(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("off", attempts=1)
    with limited_client(monkeypatch, session, settings) as client:
        assert client.get("/api/v1/not-a-route").status_code == 404

    assert session.scalar(select(RateLimitBucket)) is None


def test_general_api_limit_uses_only_validated_forwarded_address(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("enforce", attempts=1).model_copy(
        update={"trusted_proxy_cidrs": "172.18.0.0/16"}
    )
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    app = main.create_app(rate_limit_session_factory=factory)
    with TestClient(app, client=("172.18.0.5", 12345)) as client:
        first = client.get(
            "/api/v1/not-a-route",
            headers={"X-Forwarded-For": "198.51.100.24"},
        )
        other = client.get(
            "/api/v1/not-a-route",
            headers={"X-Forwarded-For": "203.0.113.77"},
        )
        repeated = client.get(
            "/api/v1/not-a-route",
            headers={"X-Forwarded-For": "198.51.100.24"},
        )

    assert first.status_code == other.status_code == 404
    assert repeated.status_code == 429
    assert len(
        list(
            session.scalars(
                select(RateLimitBucket).where(
                    RateLimitBucket.scope == "general_api_ip"
                )
            )
        )
    ) == 2


def test_general_api_limit_fails_closed_without_exposing_database_error(
    monkeypatch, session: Session
) -> None:
    settings = limit_settings("enforce", attempts=1)

    def unavailable(_self, _client_ip: str) -> None:
        raise RateLimitDecisionUnavailableError

    monkeypatch.setattr(GeneralApiRateLimitMiddleware, "_check", unavailable)
    with limited_client(monkeypatch, session, settings) as client:
        response = client.get("/api/v1/not-a-route")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Request limiting is temporarily unavailable."
    }
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-request-id"]
