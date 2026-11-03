#!/bin/sh
set -eu

image="${BOOKPILE_CADDY_IMAGE:-caddy:2.11.7-alpine}"
fixture_root="${BOOKPILE_D6_HEALTH_FIXTURE_ROOT:-${TMPDIR:-/tmp}}"
revision="0123456789abcdef0123456789abcdef01234567"
script_dir="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
evaluator="$script_dir/../deploy/evaluate-d6-health-observation.py"
compose="$script_dir/../compose.production.yaml"
fixture="$(mktemp -d "$fixture_root/bookpile-d6-health-policy.XXXXXX")"
containers=""

cleanup() {
    for container in $containers; do
        docker rm -f "$container" >/dev/null 2>&1 || true
    done
    if [ "${BOOKPILE_KEEP_D6_HEALTH_FIXTURE:-false}" = "true" ]; then
        echo "retained D6 health fixture for diagnosis: $fixture" >&2
    else
        rm -rf "$fixture"
    fi
}
trap cleanup EXIT INT TERM

mkdir -p "$fixture"
chmod 0700 "$fixture"

run_case() {
    name="$1"
    live_count="$2"
    ready_count="$3"
    expected_crossing="$4"
    case_root="$fixture/$name"
    container="bookpile-d6-health-$name-$$"
    containers="$containers $container"

    mkdir -p "$case_root/data" "$case_root/defensive" "$case_root/srv"
    cp "$script_dir/../docker/Caddyfile" "$case_root/Caddyfile"
    printf '%s\n' fixture >"$case_root/srv/index.html"
    chmod 0700 "$case_root" "$case_root/data" "$case_root/defensive" "$case_root/srv"

    docker run --rm --network none \
        --user "$(id -u):$(id -g)" \
        -e BOOKPILE_SITE_ADDRESS=:9080 \
        -e BOOKPILE_TLS_EMAIL=fixture@example.invalid \
        -e BOOKPILE_DEPLOYMENT_REVISION="$revision" \
        -v "$case_root/Caddyfile:/etc/caddy/Caddyfile:ro" \
        -v "$case_root/data:/data" \
        -v "$case_root/defensive:/var/log/bookpile" \
        -v "$case_root/srv:/srv:ro" \
        "$image" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
        >/dev/null

    docker run -d --name "$container" --network none \
        --user "$(id -u):$(id -g)" \
        -e BOOKPILE_SITE_ADDRESS=:9080 \
        -e BOOKPILE_TLS_EMAIL=fixture@example.invalid \
        -e BOOKPILE_DEPLOYMENT_REVISION="$revision" \
        -v "$case_root/Caddyfile:/etc/caddy/Caddyfile:ro" \
        -v "$case_root/data:/data" \
        -v "$case_root/defensive:/var/log/bookpile" \
        -v "$case_root/srv:/srv:ro" \
        "$image" caddy run --config /etc/caddy/Caddyfile --adapter caddyfile \
        >/dev/null

    attempt=0
    until [ "$(docker inspect --format '{{.State.Running}}' "$container")" = true ]; do
        attempt=$((attempt + 1))
        if [ "$attempt" -ge 20 ]; then
            docker logs "$container" >&2
            exit 1
        fi
        sleep 1
    done

    docker exec "$container" sh -c "
        i=0
        while [ \"\$i\" -lt $live_count ]; do
            wget -qO- -T 1 http://127.0.0.1:9080/health/live >/dev/null 2>&1 || true
            i=\$((i + 1))
        done
        i=0
        while [ \"\$i\" -lt $ready_count ]; do
            wget -qO- -T 1 http://127.0.0.1:9080/health/ready >/dev/null 2>&1 || true
            i=\$((i + 1))
        done
        i=0
        while [ \"\$i\" -lt 5 ]; do
            wget -qO- -T 1 http://127.0.0.1:9080/catalogue >/dev/null 2>&1 || true
            i=\$((i + 1))
        done
    "
    sleep 1

    log="$case_root/defensive/defensive-events.log"
    test -s "$log"
    now="$(python3 - "$log" <<'PY'
import json
import sys
from datetime import UTC, datetime

timestamps = [json.loads(line)["ts"] for line in open(sys.argv[1], encoding="utf-8")]
print(datetime.fromtimestamp(max(timestamps) + 0.01, UTC).isoformat())
PY
    )"
    summary="$(python3 "$evaluator" --now "$now" "$log")"
    python3 - "$summary" "$expected_crossing" "$live_count" "$ready_count" <<'PY'
import json
import sys

payload = json.loads(sys.argv[1])
expected = sys.argv[2]
live_count = int(sys.argv[3])
ready_count = int(sys.argv[4])
assert payload["mode"] == "dry-run"
assert payload["privacy"] == "aggregate_only"
assert payload["ignored_other_events"] == 5
assert payload["policies"]["live"]["attempts"] == live_count
assert payload["policies"]["ready"]["attempts"] == ready_count
for health_class in ("live", "ready"):
    policy = payload["policies"][health_class]
    if health_class == expected:
        assert policy["decision"] == "would_temporarily_ban"
        assert policy["crossing_clients"] == 1
    else:
        assert policy["decision"] == "allow"
        assert policy["crossing_clients"] == 0
serialized = json.dumps(payload).lower()
for forbidden in ("127.0.0.1", "client_ip", "remote_ip"):
    assert forbidden not in serialized
PY
    docker rm -f "$container" >/dev/null
}

run_case live-only 121 30 live
run_case ready-only 120 31 ready

grep -Fq 'http://127.0.0.1:8100/health/ready' "$compose"

printf '%s\n' \
    '{"classes_independent":true,"dry_run_only":true,"exact_thresholds_allow":true,"internal_probe_bypasses_caddy":true,"live_crossing_attempts":121,"raw_client_addresses_absent":true,"ready_crossing_attempts":31}'
