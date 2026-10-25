import asyncio
import json
import logging
import re
from pathlib import Path

import pytest

from bookpile_server.api.dependencies import get_private_object_storage
from bookpile_server.config import Settings
from bookpile_server.database import get_session
from bookpile_server import main
from bookpile_server import error_reporting
from bookpile_server.proxy_headers import TrustedProxyHeadersMiddleware


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
    assert compose.count("logging: *container-logging") == 4


def test_long_lived_container_logs_use_the_bounded_host_journal() -> None:
    server_root = Path(__file__).resolve().parents[1]
    compose = (server_root / "compose.production.yaml").read_text()
    journal_policy = (
        server_root
        / "deploy"
        / "journald"
        / "60-bookpile-retention.conf.example"
    ).read_text()

    assert "driver: journald" in compose
    assert 'tag: "bookpile/{{.Name}}"' in compose
    assert "driver: local" not in compose
    assert "MaxRetentionSec=14day" in journal_policy
    assert "SystemMaxUse=512M" in journal_policy
    assert "SystemKeepFree=1G" in journal_policy
    assert "MaxFileSec=1day" in journal_policy


def test_postgresql_journal_output_excludes_statements_parameters_and_detail() -> None:
    compose = (
        Path(__file__).resolve().parents[1] / "compose.production.yaml"
    ).read_text()

    assert "log_error_verbosity=terse" in compose
    assert "log_min_error_statement=panic" in compose
    assert "log_statement=none" in compose
    assert "log_parameter_max_length=0" in compose
    assert "log_parameter_max_length_on_error=0" in compose


def test_caddy_access_log_is_minimized_rotated_and_coarsens_api_traffic() -> None:
    caddyfile = (Path(__file__).resolve().parents[1] / "docker" / "Caddyfile").read_text()

    assert "roll_size 10mb" in caddyfile
    assert "roll_at 00:00" in caddyfile
    assert "roll_keep_for 336h" in caddyfile
    assert "request>uri delete" in caddyfile
    assert "request>headers delete" in caddyfile
    assert "resp_headers delete" in caddyfile
    assert "log_append @api_traffic request_path /api/*" in caddyfile
    assert "log_append @health_traffic request_path /health*" in caddyfile
    assert "log_append @browser_traffic request_path {orig_path}" in caddyfile
    assert "log_skip" not in caddyfile


def test_web_runtime_supports_time_based_access_log_rotation() -> None:
    dockerfile = (
        Path(__file__).resolve().parents[1] / "docker" / "web.Dockerfile"
    ).read_text()

    assert "FROM caddy:2.11.7-alpine AS runtime" in dockerfile
    assert "migrate-caddy-access-log-rolls.sh" in dockerfile
    assert "/usr/local/bin/migrate-caddy-access-log-rolls" in dockerfile


def test_caddy_scanner_probe_matcher_is_narrow_and_explicit() -> None:
    caddyfile = (Path(__file__).resolve().parents[1] / "docker" / "Caddyfile").read_text()
    matcher_line = next(
        line.strip()
        for line in caddyfile.splitlines()
        if line.strip().startswith("@scanner_probe path_regexp")
    )
    pattern = matcher_line.split(" ", 3)[3]

    for hostile_path in (
        "/.env",
        "/.env.production",
        "/.git/config",
        "/wp-admin",
        "/wp-admin/install.php",
        "/wp-login.php",
        "/phpMyAdmin/index.php",
    ):
        assert re.fullmatch(pattern, hostile_path)
    for application_path in (
        "/",
        "/login",
        "/libraries",
        "/.environment",
        "/.gitignore",
        "/wp-administrator",
        "/assets/wp-admin.svg",
    ):
        assert not re.fullmatch(pattern, application_path)


def test_api_runtime_leaves_forwarded_headers_to_bookpile_middleware() -> None:
    dockerfile = (Path(__file__).resolve().parents[1] / "docker" / "api.Dockerfile").read_text()

    assert '"--no-proxy-headers"' in dockerfile


def _proxied_scope(
    peer: str,
    forwarded_headers: list[bytes],
    proto_headers: list[bytes] | None = None,
) -> dict:
    captured = {}

    async def downstream(scope, _receive, _send):
        captured.update(scope)

    async def receive():
        return {"type": "http.disconnect"}

    async def send(_message):
        return None

    middleware = TrustedProxyHeadersMiddleware(
        downstream,
        _hosted_settings().trusted_proxy_networks,
    )
    scope = {
        "type": "http",
        "client": (peer, 12345),
        "scheme": "http",
        "headers": (
            [(b"x-forwarded-for", value) for value in forwarded_headers]
            + [(b"x-forwarded-proto", value) for value in (proto_headers or [])]
        ),
    }
    asyncio.run(middleware(scope, receive, send))
    return captured


def _proxied_client(peer: str, forwarded_headers: list[bytes]) -> str:
    return _proxied_scope(peer, forwarded_headers)["client"][0]


def test_trusted_proxy_supplies_one_valid_client_address() -> None:
    assert _proxied_client("172.18.0.5", [b"198.51.100.24"]) == "198.51.100.24"
    assert _proxied_client("198.51.100.24", [b"203.0.113.77"]) == "198.51.100.24"


def test_trusted_proxy_supplies_only_a_known_forwarded_scheme() -> None:
    assert _proxied_scope("172.18.0.5", [], [b"https"])["scheme"] == "https"
    assert _proxied_scope("172.18.0.5", [], [b"javascript"])["scheme"] == "http"


@pytest.mark.parametrize(
    ("peer", "headers"),
    [
        ("172.18.0.5", [b"not-an-ip"]),
        ("172.18.0.5", [b"198.51.100.24", b"203.0.113.77"]),
    ],
)
def test_untrusted_or_ambiguous_forwarded_address_fails_closed(peer, headers) -> None:
    assert _proxied_client(peer, headers) == peer


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
    assert payload["status"] == 200
    assert payload["outcome_class"] == "success"
    assert payload["response_bytes"] == int(response.headers["content-length"])
    assert len(payload["client_key"]) == 16
    assert "testclient" not in record.message
    assert "secret" not in record.message
    assert "must-not-appear" not in record.message


def test_request_log_never_retains_credentials_tokens_bodies_or_catalogue_data(
    client, caplog
) -> None:
    forbidden = (
        "session-cookie-secret",
        "bearer-secret",
        "csrf-secret",
        "reset-token-secret",
        "invite-token-secret",
        "reader@example.test",
        "private-object/covers/secret.jpg",
        "Private catalogue title",
    )
    with caplog.at_level(logging.INFO, logger="bookpile.requests"):
        response = client.post(
            "/api/v1/auth/login?invite_token=invite-token-secret",
            headers={
                "Authorization": "Bearer bearer-secret",
                "X-CSRF-Token": "csrf-secret",
                "Cookie": "bookpile_session=session-cookie-secret",
                "X-Reset-Token": "reset-token-secret",
            },
            json={
                "identifier": "reader@example.test",
                "password": "Private catalogue title",
                "object_key": "private-object/covers/secret.jpg",
            },
        )

    assert response.status_code in {401, 422}
    messages = "\n".join(
        record.message for record in caplog.records if record.name == "bookpile.requests"
    )
    assert messages
    for value in forbidden:
        assert value not in messages


def test_request_log_classifies_unmatched_and_validation_statuses(
    client, caplog
) -> None:
    expected = {
        "/api/v1/does-not-exist": (404, "not_found"),
        "/api/v1/auth/login": (422, "invalid"),
    }

    with caplog.at_level(logging.INFO, logger="bookpile.requests"):
        for path in expected:
            if path.endswith("login"):
                client.post(path, json={})
            else:
                client.get(path)

    payloads = [
        json.loads(record.message)
        for record in caplog.records
        if record.name == "bookpile.requests"
    ]
    for path, (status, outcome_class) in expected.items():
        payload = next(item for item in payloads if item["status"] == status)
        expected_route = "unmatched" if status == 404 else path
        assert payload["route"] == expected_route
        assert payload["outcome_class"] == outcome_class


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (200, "success"),
        (401, "unauthenticated"),
        (403, "forbidden"),
        (404, "not_found"),
        (409, "client_error"),
        (422, "invalid"),
        (429, "rate_limited"),
        (500, "server_error"),
    ],
)
def test_request_outcome_classes_are_aggregate_and_content_free(
    status, expected
) -> None:
    assert main._request_outcome_class(status) == expected


def test_request_client_key_is_stable_but_does_not_expose_the_address() -> None:
    secret = "private-rate-limit-secret-with-at-least-32-characters"

    first = main._request_client_key("198.51.100.24", secret)
    repeated = main._request_client_key("198.51.100.24", secret)
    other = main._request_client_key("203.0.113.77", secret)

    assert first == repeated
    assert first != other
    assert first is not None
    assert len(first) == 16
    assert "198.51.100.24" not in first
    assert main._request_client_key(None, secret) is None


def test_request_log_keys_the_validated_forwarded_client(
    monkeypatch, caplog
) -> None:
    settings = _hosted_settings()
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    app = main.create_app()
    from fastapi.testclient import TestClient

    with caplog.at_level(logging.INFO, logger="bookpile.requests"):
        with TestClient(
            app,
            base_url="https://staging.bookpile.example",
            client=("172.18.0.5", 12345),
        ) as client:
            response = client.get(
                "/health/live",
                headers={
                    "X-Forwarded-For": "198.51.100.24",
                    "X-Forwarded-Proto": "https",
                },
            )

    assert response.status_code == 200
    record = next(record for record in caplog.records if record.name == "bookpile.requests")
    payload = json.loads(record.message)
    expected = main._request_client_key(
        "198.51.100.24", settings.rate_limit_key_secret
    )
    proxy_key = main._request_client_key(
        "172.18.0.5", settings.rate_limit_key_secret
    )
    assert payload["client_key"] == expected
    assert payload["client_key"] != proxy_key


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
        "trusted_proxy_cidrs": "172.18.0.0/16",
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
    assert options["include_source_context"] is False
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
    {"trusted_proxy_cidrs": ""},
    {"trusted_proxy_cidrs": "0.0.0.0/0"},
    {"trusted_proxy_cidrs": "8.8.8.8/32"},
    {"trusted_proxy_cidrs": "100.64.0.0/10"},
    {"trusted_proxy_cidrs": "169.254.0.0/16"},
    {"trusted_proxy_cidrs": "192.0.2.0/24"},
    {"trusted_proxy_cidrs": "198.51.100.0/24"},
    {"trusted_proxy_cidrs": "203.0.113.0/24"},
    {"trusted_proxy_cidrs": "::ffff:0:0/96"},
    {"trusted_proxy_cidrs": "fe80::/10"},
    {"trusted_proxy_cidrs": "2001:db8::/32"},
])
def test_hosted_configuration_rejects_unsafe_values(changes) -> None:
    with pytest.raises(ValueError):
        _hosted_settings(**changes)


@pytest.mark.parametrize(
    "trusted_proxy_cidrs",
    [
        "10.42.0.0/16",
        "172.18.0.0/16",
        "192.168.50.0/24",
        "127.0.0.1/32",
        "fd42::/64",
        "::1/128",
    ],
)
def test_hosted_configuration_accepts_explicit_private_use_proxy_networks(
    trusted_proxy_cidrs,
) -> None:
    settings = _hosted_settings(trusted_proxy_cidrs=trusted_proxy_cidrs)

    assert settings.trusted_proxy_cidrs == trusted_proxy_cidrs


def test_hosted_configuration_accepts_implicit_smtp_tls() -> None:
    settings = _hosted_settings(smtp_starttls=False, smtp_implicit_tls=True)

    assert settings.smtp_implicit_tls


def test_configuration_rejects_two_smtp_tls_modes() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        _hosted_settings(smtp_implicit_tls=True)
