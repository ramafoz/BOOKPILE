#!/usr/bin/env bash
set -Eeuo pipefail

test_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_script="${test_directory}/../../scripts/migrate-caddy-access-log-rolls.sh"
fixture="$(mktemp -d)"
trap 'rm -rf "${fixture}"' EXIT

touch \
  "${fixture}/access-2026-10-01T00-00-00.000.log" \
  "${fixture}/access-2026-10-02T00-00-00.000.log.gz" \
  "${fixture}/access-2026-10-03T00-00-00.000-time.log" \
  "${fixture}/access-unrelated.log" \
  "${fixture}/another-2026-10-04T00-00-00.000.log.gz"

output="$(BOOKPILE_CADDY_DATA_DIR="${fixture}" sh "${source_script}")"
grep -q '"legacy_caddy_rolls_found":2' <<<"${output}"
grep -q '"legacy_caddy_rolls_migrated":2' <<<"${output}"

test -f "${fixture}/access-2026-10-01T00-00-00.000-legacy.log"
test -f "${fixture}/access-2026-10-02T00-00-00.000-legacy.log.gz"
test -f "${fixture}/access-2026-10-03T00-00-00.000-time.log"
test -f "${fixture}/access-unrelated.log"
test -f "${fixture}/another-2026-10-04T00-00-00.000.log.gz"

second_output="$(BOOKPILE_CADDY_DATA_DIR="${fixture}" sh "${source_script}")"
grep -q '"legacy_caddy_rolls_found":0' <<<"${second_output}"
grep -q '"legacy_caddy_rolls_migrated":0' <<<"${second_output}"

overflow="$(mktemp -d)"
trap 'rm -rf "${fixture}" "${overflow}"' EXIT
touch \
  "${overflow}/access-2026-10-01T00-00-00.000.log" \
  "${overflow}/access-2026-10-02T00-00-00.000.log"
if BOOKPILE_CADDY_DATA_DIR="${overflow}" \
  BOOKPILE_CADDY_LEGACY_LOG_MIGRATION_MAX=1 \
  sh "${source_script}" >/dev/null 2>&1; then
  echo "Expected the migration bound to reject excess legacy rolls" >&2
  exit 1
fi
test -f "${overflow}/access-2026-10-01T00-00-00.000.log"
test -f "${overflow}/access-2026-10-02T00-00-00.000.log"

collision="$(mktemp -d)"
trap 'rm -rf "${fixture}" "${overflow}" "${collision}"' EXIT
touch \
  "${collision}/access-2026-10-01T00-00-00.000.log" \
  "${collision}/access-2026-10-01T00-00-00.000-legacy.log"
if BOOKPILE_CADDY_DATA_DIR="${collision}" sh "${source_script}" >/dev/null 2>&1; then
  echo "Expected an existing target to stop migration" >&2
  exit 1
fi
test -f "${collision}/access-2026-10-01T00-00-00.000.log"

echo "Caddy legacy log migration tests passed."
