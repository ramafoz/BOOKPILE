#!/usr/bin/env bash
set -Eeuo pipefail

root="$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)"
fixture="$root/tests/health-events.log"

for health_class in live ready; do
  output="$(
    fail2ban-regex \
      --usedns=no \
      "$fixture" \
      "$root/filter.d/bookpile-health-${health_class}.conf"
  )"
  if ! grep -Eq 'Lines: 2 lines, 0 ignored, 1 matched, 1 missed' <<<"$output"; then
    printf '%s\n' "$output" >&2
    echo "Unexpected ${health_class} filter result." >&2
    exit 1
  fi
done

printf '%s\n' \
  '{"live_matches":1,"ready_matches":1,"classes_independent":true}'
