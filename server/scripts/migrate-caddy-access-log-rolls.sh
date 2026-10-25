#!/bin/sh
set -eu

data_dir="${BOOKPILE_CADDY_DATA_DIR:-/data}"
max_files="${BOOKPILE_CADDY_LEGACY_LOG_MIGRATION_MAX:-100}"

case "$max_files" in
    ''|*[!0-9]*)
        echo "BOOKPILE_CADDY_LEGACY_LOG_MIGRATION_MAX must be a positive integer" >&2
        exit 2
        ;;
esac
if [ "$max_files" -lt 1 ]; then
    echo "BOOKPILE_CADDY_LEGACY_LOG_MIGRATION_MAX must be at least 1" >&2
    exit 2
fi
if [ ! -d "$data_dir" ]; then
    echo "Caddy data directory does not exist: $data_dir" >&2
    exit 1
fi

is_legacy_roll() {
    printf '%s\n' "$1" | grep -Eq \
        '^access-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}-[0-9]{2}-[0-9]{2}\.[0-9]{3}\.log(\.gz)?$'
}

legacy_count=0
for source in "$data_dir"/access-*.log "$data_dir"/access-*.log.gz; do
    [ -e "$source" ] || continue
    basename="${source##*/}"
    if is_legacy_roll "$basename"; then
        legacy_count=$((legacy_count + 1))
    fi
done

if [ "$legacy_count" -gt "$max_files" ]; then
    echo "Refusing to migrate $legacy_count legacy Caddy rolls; limit is $max_files" >&2
    exit 1
fi

# Refuse every collision before changing any name, so a failed preflight leaves
# the complete legacy set untouched.
for source in "$data_dir"/access-*.log "$data_dir"/access-*.log.gz; do
    [ -e "$source" ] || continue
    basename="${source##*/}"
    is_legacy_roll "$basename" || continue
    case "$source" in
        *.log.gz) target="${source%.log.gz}-legacy.log.gz" ;;
        *.log) target="${source%.log}-legacy.log" ;;
    esac
    if [ -e "$target" ]; then
        echo "Refusing to overwrite existing migrated Caddy roll: $target" >&2
        exit 1
    fi
done

migrated_count=0
for source in "$data_dir"/access-*.log "$data_dir"/access-*.log.gz; do
    [ -e "$source" ] || continue
    basename="${source##*/}"
    is_legacy_roll "$basename" || continue
    case "$source" in
        *.log.gz) target="${source%.log.gz}-legacy.log.gz" ;;
        *.log) target="${source%.log}-legacy.log" ;;
    esac
    mv "$source" "$target"
    migrated_count=$((migrated_count + 1))
done

printf '{"legacy_caddy_rolls_found":%s,"legacy_caddy_rolls_migrated":%s}\n' \
    "$legacy_count" "$migrated_count"
