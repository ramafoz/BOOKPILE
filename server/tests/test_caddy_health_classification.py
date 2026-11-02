from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "server" / "docker" / "Caddyfile"
COMPOSE = ROOT / "server" / "compose.production.yaml"
VALIDATOR = ROOT / "server" / "deploy" / "validate-caddy-defensive-log.py"
REVISION = "0123456789abcdef0123456789abcdef01234567"


def _validator_module():
    spec = importlib.util.spec_from_file_location("d6_validator", VALIDATOR)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _event(**changes: object) -> dict[str, object]:
    event: dict[str, object] = {
        "ts": 1_799_000_000.0,
        "level": "info",
        "logger": "http.log.access.d6_defensive",
        "msg": "handled request",
        "deployment_revision": REVISION,
        "health_class": "live",
        "defensive_decision": "observed",
        "client_ip": "192.0.2.10",
    }
    event.update(changes)
    return event


def test_health_paths_are_mapped_once_to_three_fixed_classes() -> None:
    caddyfile = CADDYFILE.read_text(encoding="utf-8")
    map_block = caddyfile.split(
        "map {http.request.uri.path} {bookpile_health_class} {", 1
    )[1].split("}", 1)[0]
    mappings = {
        parts[0]: parts[1]
        for line in map_block.splitlines()
        if len(parts := line.split()) == 2
    }

    assert mappings == {
        "/health/live": "live",
        "/health/ready": "ready",
        "default": "other",
    }
    assert caddyfile.count("log_append health_class") == 1
    assert "log_name access_log d6_defensive" in caddyfile


def test_defensive_log_deletes_variable_request_and_response_fields() -> None:
    caddyfile = CADDYFILE.read_text(encoding="utf-8")
    defensive = caddyfile.split("log d6_defensive {", 1)[1].split(
        "\n\t}\n", 1
    )[0]

    for field in (
        "request",
        "bytes_read",
        "user_id",
        "duration",
        "size",
        "status",
        "resp_headers",
        "request_path",
        "event_class",
        "policy_scope",
    ):
        assert f"{field} delete" in defensive
    for forbidden in ("{uri}", "{query}", "{cookie", "{header", "request_id"):
        assert forbidden not in defensive.lower()


def test_validator_accepts_only_the_fixed_schema_and_values() -> None:
    validator = _validator_module()
    line = json.dumps(_event())

    assert validator.validate_lines([line]) == {"live": 1}
    for invalid in (
        _event(health_class="unexpected"),
        _event(defensive_decision="blocked"),
        _event(level="debug"),
        _event(client_ip="not-an-ip"),
        _event(uri="/health/live?secret=value"),
        _event(cookie="secret"),
    ):
        with pytest.raises(validator.DefensiveLogValidationError):
            validator.validate_event(invalid)


def test_internal_docker_healthcheck_bypasses_public_caddy_policy() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")
    caddyfile = CADDYFILE.read_text(encoding="utf-8")
    api_service = compose.split("\n  api:\n", 1)[1].split("\n  email-worker:\n", 1)[0]
    web_service = compose.split("\n  web:\n", 1)[1].split("\nnetworks:\n", 1)[0]

    assert "http://127.0.0.1:8100/health/ready" in api_service
    assert "source: /var/log/bookpile" not in api_service
    assert "source: /var/log/bookpile" in web_service
    assert "target: /var/log/bookpile" in web_service
    assert "create_host_path: false" in web_service
    assert "root * /srv" in caddyfile
    assert "output file /var/log/bookpile/defensive-events.log" in caddyfile
