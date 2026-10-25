#!/bin/sh
set -eu

image="${BOOKPILE_CADDY_IMAGE:-caddy:2.11.7-alpine}"
container="bookpile-caddy-retention-$$"
fixture_root="${BOOKPILE_CADDY_RETENTION_FIXTURE_ROOT:-${TMPDIR:-/tmp}}"
mkdir -p "$fixture_root"
fixture="$(mktemp -d "$fixture_root/bookpile-caddy-retention.XXXXXX")"
config="$fixture/Caddyfile"

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
    if [ "${BOOKPILE_KEEP_CADDY_RETENTION_FIXTURE:-false}" = "true" ]; then
        echo "retained Caddy fixture for diagnosis: $fixture" >&2
    else
        rm -rf "$fixture"
    fi
}
trap cleanup EXIT INT TERM

cat > "$config" <<'EOF'
{
    admin off
    auto_https off
}

:9080 {
    log {
        output file /fixture/access.log {
            roll_size 10mb
            roll_interval 2s
            roll_uncompressed
            roll_keep 10
            roll_keep_for 24h
        }
        format json
    }
    respond "fixture"
}
EOF

old_stamp="$(date -u -d '2 days ago' +%Y-%m-%dT%H-%M-%S.000)"
new_stamp="$(date -u +%Y-%m-%dT%H-%M-%S.000)"
old_file="$fixture/access-$old_stamp-time.log"
new_file="$fixture/access-$new_stamp-time.log"
legacy_old_file="$fixture/access-$old_stamp.log.gz"
legacy_new_file="$fixture/access-$new_stamp.log.gz"
printf '%s\n' 'BOOKPILE_OLD_RETENTION_FIXTURE' > "$old_file"
printf '%s\n' 'BOOKPILE_NEW_RETENTION_FIXTURE' > "$new_file"
printf '%s\n' 'BOOKPILE_LEGACY_OLD_RETENTION_FIXTURE' > "$legacy_old_file"
printf '%s\n' 'BOOKPILE_LEGACY_NEW_RETENTION_FIXTURE' > "$legacy_new_file"

BOOKPILE_CADDY_DATA_DIR="$fixture" \
    sh "$(dirname "$0")/migrate-caddy-access-log-rolls.sh" >/dev/null

if [ -e "$legacy_old_file" ] || [ -e "$legacy_new_file" ]; then
    echo "legacy Caddy roll name survived migration" >&2
    exit 1
fi

docker run -d --name "$container" --network none \
    --user "$(id -u):$(id -g)" \
    -v "$fixture:/fixture" \
    "$image" caddy run --config /fixture/Caddyfile --adapter caddyfile \
    >/dev/null

sleep 1
if [ "$(docker inspect --format '{{.State.Running}}' "$container")" != "true" ]; then
    docker inspect --format \
        'fixture container exited: code={{.State.ExitCode}} error={{.State.Error}}' \
        "$container" >&2
    docker logs "$container" >&2
    find "$fixture" -maxdepth 1 -type f -print >&2
    if [ -f "$fixture/access.log" ]; then
        tail -n 20 "$fixture/access.log" >&2
    fi
    exit 1
fi

attempt=0
until docker exec "$container" wget -qO- http://127.0.0.1:9080/ >/dev/null; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 20 ]; then
        docker logs "$container" >&2
        exit 1
    fi
    sleep 1
done

# Let the fixture's temporal timer create a new roll and run expiry cleanup.
sleep 4
docker exec "$container" wget -qO- http://127.0.0.1:9080/ >/dev/null
sleep 1

if grep -R -q 'BOOKPILE_OLD_RETENTION_FIXTURE' "$fixture"; then
    echo "old fixture survived temporal expiry" >&2
    exit 1
fi
if grep -R -q 'BOOKPILE_LEGACY_OLD_RETENTION_FIXTURE' "$fixture"; then
    echo "migrated old legacy fixture survived temporal expiry" >&2
    exit 1
fi
if ! grep -R -q 'BOOKPILE_NEW_RETENTION_FIXTURE' "$fixture"; then
    echo "new fixture was removed before expiry" >&2
    exit 1
fi
if ! grep -R -q 'BOOKPILE_LEGACY_NEW_RETENTION_FIXTURE' "$fixture"; then
    echo "migrated new legacy fixture was removed before expiry" >&2
    exit 1
fi

printf '%s\n' \
    '{"caddy_time_rotation":true,"legacy_roll_migration":true,"new_fixture_readable":true,"old_fixture_absent":true}'
