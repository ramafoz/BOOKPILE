import json
import logging

import pytest

from bookpile_server.api.dependencies import get_private_object_storage
from bookpile_server.config import Settings
from bookpile_server.database import get_session
from bookpile_server import main


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


@pytest.mark.parametrize("changes", [
    {"allowed_hosts": "*"},
    {"allowed_hosts": "other.example"},
    {"public_base_url": "https://user:password@staging.bookpile.example"},
    {"public_base_url": "https://staging.bookpile.example/application"},
    {"database_url": "sqlite:///bookpile.db"},
    {"api_docs_enabled": True},
    {"deployment_revision": "development"},
])
def test_hosted_configuration_rejects_unsafe_values(changes) -> None:
    with pytest.raises(ValueError):
        _hosted_settings(**changes)
