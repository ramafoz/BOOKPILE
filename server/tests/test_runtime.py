import json
import logging
from pathlib import Path
from pathlib import Path

import pytest

from bookpile_server.api.dependencies import get_private_object_storage
from bookpile_server.config import Settings
from bookpile_server.database import get_session
from bookpile_server import main
from bookpile_server import error_reporting


class UnavailableObjects:
    def check_ready(self) -> None:
        raise OSError("not mounted")


class UnavailableDatabase:
    def execute(self, _statement) -> None:
        raise OSError("not connected")


def test_readiness_reports_dependencies_without_exposing_exceptions(client) -> None:
    app = client.app
    original_session = app.dependency_overrides[get_session]
    app.dependency_overrides[get_session] = lambda: UnavailableDatabase()
    app.dependency_overrides[get_private_object_storage] = lambda: UnavailableObjects()
    try:
        response = client.get("/health/ready")
    finally:
        app.dependency_overrides[get_session] = original_session
        app.dependency_overrides.pop(get_private_object_storage, None)

    assert response.status_code == 503
    assert response.json() == {
        "status": "unavailable",
        "revision": "development",
        "checks": {"database": "unavailable", "private_objects": "unavailable"},
    }
    assert "not mounted" not in response.text
    assert "not connected" not in response.text


def test_untrusted_host_is_rejected(client) -> None:
    assert client.get("/health", headers={"Host": "attacker.example"}).status_code == 400


def test_production_compose_preserves_host_validation_and_explicit_egress() -> None:
    compose = (Path(__file__).resolve().parents[1] / "compose.production.yaml").read_text()

    assert "headers={'Host': host}" in compose
    assert "BOOKPILE_SERVER_ALLOWED_HOSTS" in compose
    assert compose.count("networks: [backend, egress]") == 4
    assert "backend:\n    internal: true" in compose


def test_production_healthcheck_uses_the_configured_trusted_host() -> None:
    compose = (Path(__file__).resolve().parents[1] / "compose.production.yaml").read_text()

    assert "BOOKPILE_SERVER_ALLOWED_HOSTS" in compose
    assert "headers={'Host': host}" in compose


def test_request_log_uses_route_template_and_omits_query(client, caplog) -> None:
    with caplog.at_level(logging.INFO, logger="bookpile.requests"):
        response = client.get("/health/live?secret=must-not-appear")

    record = next(record for record in caplog.records if record.name == "bookpile.requests")
    payload = json.loads(record.message)
    assert payload["route"] == "/health/live"
    assert payload["request_id"] == response.headers["x-request-id"]
    assert "secret" not in record.message
    assert "must-not-appear" not in record.message


def _hosted_settings(**changes) -> Settings:
    values = {
        "environment": "staging",
        "rate_limit_key_secret": "private-rate-limit-secret-with-at-least-32-characters",
        "session_cookie_secure": True,
        "public_base_url": "https://staging.bookpile.example",
        "database_url": "postgresql+psycopg://bookpile:private@db/bookpile",
        "deployment_revision": "git-1234567",
        "api_docs_enabled": False,
        "allowed_hosts": "staging.bookpile.example",
        "private_object_backend": "s3",
        "private_object_s3_endpoint_url": "https://objects.example",
        "private_object_s3_region": "eu-test-1",
        "private_object_s3_bucket": "bookpile-private",
        "private_object_s3_access_key_id": "test-access-key",
        "private_object_s3_secret_access_key": "test-secret-key",
        "smtp_starttls": True,
        "smtp_username": "smtp-user",
        "smtp_password": "smtp-password",
        "email_delivery_mode": "outbox",
        "email_outbox_encryption_secret": "private-outbox-secret-with-at-least-32-characters",
    }
    values.update(changes)
    return Settings(**values)


def test_hosted_app_hides_docs_and_adds_transport_security(monkeypatch) -> None:
    monkeypatch.setattr(main, "get_settings", lambda: _hosted_settings())
    app = main.create_app()
    from fastapi.testclient import TestClient
    with TestClient(app, base_url="https://staging.bookpile.example") as client:
        assert client.get("/docs").status_code == 404
        response = client.get("/health/live")
    assert response.headers["strict-transport-security"].startswith("max-age=31536000")


def test_hosted_unhandled_error_is_correlatable_without_leaking_message(
    monkeypatch, caplog
) -> None:
    captured = []
    monkeypatch.setattr(
        main,
        "capture_unhandled_request_error",
        lambda exc, request_id, settings: captured.append(
            (exc, request_id, settings.deployment_revision)
        ),
    )
    monkeypatch.setattr(main, "get_settings", lambda: _hosted_settings())
    app = main.create_app()

    @app.get("/test-unhandled")
    def fail():
        raise RuntimeError("private-value-must-not-appear")

    from fastapi.testclient import TestClient

    with TestClient(
        app,
        base_url="https://staging.bookpile.example",
        raise_server_exceptions=False,
    ) as client:
        response = client.get("/test-unhandled")

    assert response.status_code == 500
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    assert "RuntimeError" in caplog.text
    assert "private-value-must-not-appear" not in caplog.text
    assert len(captured) == 1
    assert isinstance(captured[0][0], RuntimeError)
    assert captured[0][1] == response.headers["x-request-id"]
    assert captured[0][2] == "git-1234567"


def test_error_reporting_scrubber_keeps_stack_but_removes_private_context() -> None:
    event = {
        "request": {"url": "https://example.test/private?token=secret"},
        "user": {"email": "reader@example.test"},
        "breadcrumbs": {"values": [{"message": "private title"}]},
        "contexts": {"response": {"body": "private body"}},
        "extra": {"library": "private library"},
        "message": "private message",
        "server_name": "private-hostname",
        "tags": {
            "bookpile.correlation_id": "request-123",
            "untrusted": "private tag",
        },
        "exception": {
            "values": [
                {
                    "type": "RuntimeError",
                    "value": "private exception value",
                    "stacktrace": {
                        "frames": [{"filename": "bookpile_server/main.py", "lineno": 1}]
                    },
                }
            ]
        },
    }

    scrubbed = error_reporting.scrub_error_event(event, {})
    serialized = json.dumps(scrubbed)

    assert scrubbed["exception"]["values"][0]["type"] == "RuntimeError"
    assert scrubbed["exception"]["values"][0]["value"] == "[redacted]"
    assert "stacktrace" in scrubbed["exception"]["values"][0]
    assert scrubbed["tags"] == {"bookpile.correlation_id": "request-123"}
    assert scrubbed["transaction"] == "unhandled_request"
    assert "private" not in serialized
    assert "secret" not in serialized


def test_error_reporting_initialization_disables_automatic_data_collection(
    monkeypatch,
) -> None:
    options = {}
    monkeypatch.setattr(
        error_reporting.sentry_sdk,
        "init",
        lambda **kwargs: options.update(kwargs),
    )
    monkeypatch.setattr(error_reporting.sentry_sdk, "is_initialized", lambda: True)
    settings = _hosted_settings(
        error_reporting_dsn="https://public-key@errors.example.test/123"
    )

    assert error_reporting.initialize_error_reporting(settings)
    assert options["default_integrations"] is False
    assert options["auto_enabling_integrations"] is False
    assert options["traces_sample_rate"] == 0.0
    assert options["send_default_pii"] is False
    assert options["include_local_variables"] is False
    assert options["max_request_body_size"] == "never"


@pytest.mark.parametrize("changes", [
    {"allowed_hosts": "*"},
    {"allowed_hosts": "other.example"},
    {"public_base_url": "https://user:password@staging.bookpile.example"},
    {"public_base_url": "https://staging.bookpile.example/application"},
    {"database_url": "sqlite:///bookpile.db"},
    {"api_docs_enabled": True},
    {"deployment_revision": "development"},
    {"private_object_backend": "filesystem"},
    {"private_object_s3_endpoint_url": "http://objects.example"},
    {"error_reporting_dsn": "http://errors.example.test/123"},
])
def test_hosted_configuration_rejects_unsafe_values(changes) -> None:
    with pytest.raises(ValueError):
        _hosted_settings(**changes)


def test_hosted_configuration_accepts_implicit_smtp_tls() -> None:
    settings = _hosted_settings(smtp_starttls=False, smtp_implicit_tls=True)

    assert settings.smtp_implicit_tls


def test_configuration_rejects_two_smtp_tls_modes() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _hosted_settings(smtp_implicit_tls=True)
