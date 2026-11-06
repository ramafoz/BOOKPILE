#!/bin/sh
set -eu

image="${BOOKPILE_CADDY_IMAGE:-caddy:2.11.7-alpine}"
container="bookpile-caddy-health-classification-$$"
fixture_root="${BOOKPILE_CADDY_HEALTH_FIXTURE_ROOT:-${TMPDIR:-/tmp}}"
mkdir -p "$fixture_root"
fixture="$(mktemp -d "$fixture_root/bookpile-caddy-health.XXXXXX")"
revision="0123456789abcdef0123456789abcdef01234567"

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    if [ "${BOOKPILE_KEEP_CADDY_HEALTH_FIXTURE:-false}" = "true" ]; then
        echo "retained Caddy health fixture for diagnosis: $fixture" >&2
    else
        rm -rf "$fixture"
    fi
}
trap cleanup EXIT INT TERM

mkdir -p "$fixture/data" "$fixture/defensive" "$fixture/srv"
cp "$(dirname "$0")/../docker/Caddyfile" "$fixture/Caddyfile"
printf '%s\n' 'fixture' >"$fixture/srv/index.html"
chmod 0700 "$fixture" "$fixture/data" "$fixture/defensive" "$fixture/srv"

docker run --rm --network none \
    --user "$(id -u):$(id -g)" \
    -e BOOKPILE_SITE_ADDRESS=:9080 \
    -e BOOKPILE_TLS_EMAIL=fixture@example.invalid \
    -e BOOKPILE_DEPLOYMENT_REVISION="$revision" \
    -v "$fixture/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$fixture/data:/data" \
    -v "$fixture/defensive:/var/log/bookpile" \
    -v "$fixture/srv:/srv:ro" \
    "$image" caddy validate --config /etc/caddy/Caddyfile --adapter caddyfile \
    >/dev/null

docker run -d --name "$container" --network none \
    --user "$(id -u):$(id -g)" \
    -e BOOKPILE_SITE_ADDRESS=:9080 \
    -e BOOKPILE_TLS_EMAIL=fixture@example.invalid \
    -e BOOKPILE_DEPLOYMENT_REVISION="$revision" \
    -v "$fixture/Caddyfile:/etc/caddy/Caddyfile:ro" \
    -v "$fixture/data:/data" \
    -v "$fixture/defensive:/var/log/bookpile" \
    -v "$fixture/srv:/srv:ro" \
    "$image" caddy run --config /etc/caddy/Caddyfile --adapter caddyfile \
    >/dev/null

attempt=0
until [ "$(docker inspect --format '{{.State.Running}}' "$container")" = "true" ]; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 20 ]; then
        docker logs "$container" >&2
        exit 1
    fi
    sleep 1
done

# The health upstream is intentionally absent: D6 classification belongs to
# Caddy and must still be emitted when Python is unavailable. wget's 502 exit
# is therefore expected for the first two requests.
docker exec "$container" wget -qO- \
    'http://127.0.0.1:9080/health/live?secret=live-query-must-not-survive' \
    >/dev/null 2>&1 || true
docker exec "$container" wget -qO- \
    'http://127.0.0.1:9080/health/ready?secret=ready-query-must-not-survive' \
    >/dev/null 2>&1 || true
docker exec "$container" wget -qO- \
    'http://127.0.0.1:9080/catalogue?secret=other-query-must-not-survive' \
    >/dev/null
docker exec "$container" wget -qO- \
    'http://127.0.0.1:9080/.env?secret=scanner-query-must-not-survive' \
    >/dev/null 2>&1 || true
sleep 1

defensive_log="$fixture/defensive/defensive-events.log"
test -s "$defensive_log"
summary="$(python3 "$(dirname "$0")/../deploy/validate-caddy-defensive-log.py" \
    "$defensive_log")"
if [ "$summary" != '{"health_classes": {"live": 1, "other": 2, "ready": 1}, "scanner_probes": 1}' ]; then
    echo "unexpected D6 class counts: $summary" >&2
    cat "$defensive_log" >&2
    exit 1
fi

if grep -Eq 'live-query|ready-query|other-query|scanner-query|secret=|/health/|/catalogue|/\.env|Cookie|Authorization' \
    "$defensive_log"; then
    echo "private request data survived in the defensive log" >&2
    cat "$defensive_log" >&2
    exit 1
fi

# Prove fail-closed handling of future or misspelled labels.
python3 - "$defensive_log" "$fixture/unexpected.jsonl" <<'PY'
import json
import sys

source, target = sys.argv[1:]
event = json.loads(open(source, encoding="utf-8").readline())
event["health_class"] = "unexpected"
with open(target, "w", encoding="utf-8") as stream:
    stream.write(json.dumps(event) + "\n")
PY
if python3 "$(dirname "$0")/../deploy/validate-caddy-defensive-log.py" \
    "$fixture/unexpected.jsonl" >/dev/null 2>&1; then
    echo "validator accepted an unexpected health class" >&2
    exit 1
fi

printf '%s\n' \
    '{"caddy_config_valid":true,"classes_mutually_exclusive":true,"internal_probe_bypasses_caddy":true,"private_request_fields_absent":true,"scanner_label_fixed":true,"unexpected_labels_rejected":true}'
