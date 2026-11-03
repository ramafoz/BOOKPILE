from __future__ import annotations

import gzip
import json
import runpy
from datetime import UTC, datetime
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
EVALUATOR = ROOT / "server" / "deploy" / "evaluate-d6-health-observation.py"
REHEARSAL = ROOT / "server" / "scripts" / "rehearse-d6-health-policy-dry-run.sh"
COMPOSE = ROOT / "server" / "compose.production.yaml"
REVISION = "0123456789abcdef0123456789abcdef01234567"
SECOND_REVISION = "89abcdef0123456789abcdef0123456789abcdef"
NOW = datetime(2026, 11, 3, 20, 0, tzinfo=UTC)


def _module() -> dict[str, object]:
    return runpy.run_path(str(EVALUATOR))


def _event(
    health_class: str,
    *,
    client_ip: str = "192.0.2.10",
    seconds_ago: float = 1,
    revision: str = REVISION,
) -> str:
    return json.dumps(
        {
            "ts": NOW.timestamp() - seconds_ago,
            "level": "info",
            "logger": "http.log.access.d6_defensive",
            "msg": "handled request",
            "deployment_revision": revision,
            "health_class": health_class,
            "defensive_decision": "observed",
            "client_ip": client_ip,
        }
    )


def _evaluate(lines: list[str]) -> dict[str, object]:
    return _module()["evaluate"](lines, now=NOW)  # type: ignore[index,operator]


def test_exact_thresholds_allow_and_other_is_never_counted() -> None:
    result = _evaluate(
        [_event("live")] * 120
        + [_event("ready")] * 30
        + [_event("other")] * 25
    )

    assert result["ignored_other_events"] == 25
    assert result["policies"] == {
        "live": {
            "attempts": 120,
            "crossing_clients": 0,
            "decision": "allow",
            "deployment_revisions": [],
            "max_attempts_per_client": 120,
            "threshold": 120,
        },
        "ready": {
            "attempts": 30,
            "crossing_clients": 0,
            "decision": "allow",
            "deployment_revisions": [],
            "max_attempts_per_client": 30,
            "threshold": 30,
        },
    }


def test_live_and_ready_crossings_are_independent() -> None:
    live = _evaluate([_event("live")] * 121 + [_event("ready")] * 30)
    ready = _evaluate([_event("live")] * 120 + [_event("ready")] * 31)

    assert live["policies"]["live"]["decision"] == "would_temporarily_ban"
    assert live["policies"]["ready"]["decision"] == "allow"
    assert ready["policies"]["live"]["decision"] == "allow"
    assert ready["policies"]["ready"]["decision"] == "would_temporarily_ban"


def test_distinct_clients_are_not_combined() -> None:
    result = _evaluate(
        [_event("live", client_ip="192.0.2.10")] * 61
        + [_event("live", client_ip="192.0.2.11")] * 60
    )

    assert result["policies"]["live"] == {
        "attempts": 121,
        "crossing_clients": 0,
        "decision": "allow",
        "deployment_revisions": [],
        "max_attempts_per_client": 61,
        "threshold": 120,
    }


def test_ipv6_forms_are_canonicalized_and_revision_attribution_is_preserved() -> None:
    result = _evaluate(
        [
            _event("live", client_ip="2001:0db8:0:0:0:0:0:1", revision=REVISION)
        ]
        * 61
        + [
            _event("live", client_ip="2001:db8::1", revision=SECOND_REVISION)
        ]
        * 60
    )

    assert result["policies"]["live"] == {
        "attempts": 121,
        "crossing_clients": 1,
        "decision": "would_temporarily_ban",
        "deployment_revisions": [REVISION, SECOND_REVISION],
        "max_attempts_per_client": 121,
        "threshold": 120,
    }
    serialized = json.dumps(result)
    assert "2001:db8" not in serialized
    assert "192.0.2" not in serialized


def test_events_outside_the_fixed_window_do_not_count() -> None:
    result = _evaluate(
        [_event("ready", seconds_ago=60.001)] * 31
        + [_event("ready", seconds_ago=59.999)] * 30
    )

    assert result["policies"]["ready"]["attempts"] == 30
    assert result["policies"]["ready"]["decision"] == "allow"


def test_malformed_and_future_events_fail_closed() -> None:
    module = _module()
    error = module["HealthObservationError"]

    with pytest.raises(error):
        module["evaluate"](["not-json"], now=NOW)
    with pytest.raises(error):
        module["evaluate"](
            [_event("live", seconds_ago=-2)],
            now=NOW,
        )


def test_real_image_rehearsal_is_dry_run_and_uses_independent_boundaries() -> None:
    script = REHEARSAL.read_text(encoding="utf-8")

    assert "run_case live-only 121 30 live" in script
    assert "run_case ready-only 120 31 ready" in script
    assert 'payload["mode"] == "dry-run"' in script
    for forbidden in ("fail2ban-client", "iptables", "nft "):
        assert forbidden not in script


def test_internal_ready_probe_bypasses_the_public_caddy_policy() -> None:
    compose = COMPOSE.read_text(encoding="utf-8")

    assert "http://127.0.0.1:8100/health/ready" in compose


def test_active_source_includes_compressed_rolls_without_double_counting(
    tmp_path: Path,
) -> None:
    module = _module()
    active = tmp_path / "defensive-events.log"
    rolled = tmp_path / "defensive-events-2026-11-03T20-00-00Z-rotation.log.gz"
    active.write_text(_event("ready") + "\n", encoding="utf-8")
    with gzip.open(rolled, "wt", encoding="utf-8") as stream:
        stream.write("\n".join([_event("ready")] * 30) + "\n")

    lines = module["_read_sources"]([active, active])
    result = module["evaluate"](lines, now=NOW)

    assert result["policies"]["ready"] == {
        "attempts": 31,
        "crossing_clients": 1,
        "decision": "would_temporarily_ban",
        "deployment_revisions": [REVISION],
        "max_attempts_per_client": 31,
        "threshold": 30,
    }


def test_malformed_compressed_roll_fails_closed(tmp_path: Path) -> None:
    module = _module()
    active = tmp_path / "defensive-events.log"
    rolled = tmp_path / "defensive-events-broken.log.gz"
    active.write_text(_event("live") + "\n", encoding="utf-8")
    rolled.write_text("not gzip", encoding="utf-8")

    with pytest.raises(OSError):
        list(module["_read_sources"]([active]))


def test_rotation_during_source_read_requires_repeating_the_phase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _module()
    active = tmp_path / "defensive-events.log"
    rolled = tmp_path / "defensive-events-old.log.gz"
    active.write_text(_event("live") + "\n", encoding="utf-8")
    with gzip.open(rolled, "wt", encoding="utf-8") as stream:
        stream.write(_event("live") + "\n")
    original_open = module["gzip"].open

    def rotate_while_opening(*args, **kwargs):
        active.unlink()
        active.write_text(_event("ready") + "\n", encoding="utf-8")
        return original_open(*args, **kwargs)

    monkeypatch.setattr(module["gzip"], "open", rotate_while_opening)

    with pytest.raises(
        module["HealthObservationError"],
        match="rotated during evaluation",
    ):
        list(module["_read_sources"]([active]))
