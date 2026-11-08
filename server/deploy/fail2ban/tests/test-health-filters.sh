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
  if ! grep -Eq 'Lines: 3 lines, 0 ignored, 1 matched, 2 missed' <<<"$output"; then
    printf '%s\n' "$output" >&2
    echo "Unexpected ${health_class} filter result." >&2
    exit 1
  fi
done

scanner_output="$(
  fail2ban-regex \
    --usedns=no \
    "$fixture" \
    "$root/filter.d/bookpile-scanner-probe.conf"
)"
if ! grep -Eq 'Lines: 3 lines, 0 ignored, 1 matched, 2 missed' <<<"$scanner_output"; then
  printf '%s\n' "$scanner_output" >&2
  echo 'Unexpected scanner filter result.' >&2
  exit 1
fi

volume_output="$(
  fail2ban-regex \
    --usedns=no \
    "$fixture" \
    "$root/filter.d/bookpile-edge-volume.conf"
)"
if ! grep -Eq 'Lines: 3 lines, 0 ignored, 3 matched, 0 missed' <<<"$volume_output"; then
  printf '%s\n' "$volume_output" >&2
  echo 'Unexpected edge-volume filter result.' >&2
  exit 1
fi

printf '%s\n' \
  '{"live_matches":1,"ready_matches":1,"scanner_matches":1,"volume_matches":3,"classes_independent":true}'
