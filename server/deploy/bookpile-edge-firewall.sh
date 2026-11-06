#!/usr/bin/env bash
set -Eeuo pipefail

readonly TABLE_FAMILY='inet'
readonly TABLE_NAME='bookpile'
readonly POLICY_FILE='/usr/local/share/bookpile/bookpile-health-enforcement.nft'
readonly VALIDATOR='/usr/local/libexec/bookpile/validate-bookpile-nftables'

usage() {
  echo "Usage: $0 ensure | check | destroy | flush <live|ready> | ban <live|ready> <IPv4> | unban <live|ready> <IPv4>" >&2
  exit 2
}

[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }
command -v nft >/dev/null

mode="${1:-}"
shift || true

set_name() {
  case "$1" in
    live) printf 'health_live_ipv4\n' ;;
    ready) printf 'health_ready_ipv4\n' ;;
    *) usage ;;
  esac
}

validate_ipv4() {
  python3 - "$1" <<'PY'
import ipaddress
import sys

value = ipaddress.ip_address(sys.argv[1])
if value.version != 4:
    raise SystemExit(1)
PY
}

check_policy() {
  nft -j --stateless list table "$TABLE_FAMILY" "$TABLE_NAME" |
    python3 "$VALIDATOR" >/dev/null
}

ensure_policy() {
  if nft list table "$TABLE_FAMILY" "$TABLE_NAME" >/dev/null 2>&1; then
    check_policy
    return
  fi
  [[ -f "$POLICY_FILE" && ! -L "$POLICY_FILE" ]] || {
    echo 'Missing or unsafe BOOKPILE nftables policy file.' >&2
    exit 1
  }
  nft --check --file "$POLICY_FILE"
  nft --file "$POLICY_FILE"
  check_policy
}

case "$mode" in
  ensure)
    [[ $# -eq 0 ]] || usage
    ensure_policy
    ;;
  check)
    [[ $# -eq 0 ]] || usage
    check_policy
    ;;
  destroy)
    [[ $# -eq 0 ]] || usage
    if nft list table "$TABLE_FAMILY" "$TABLE_NAME" >/dev/null 2>&1; then
      check_policy
      nft delete table "$TABLE_FAMILY" "$TABLE_NAME"
    fi
    ;;
  flush)
    [[ $# -eq 1 ]] || usage
    policy_set="$(set_name "$1")"
    check_policy
    nft flush set "$TABLE_FAMILY" "$TABLE_NAME" "$policy_set"
    ;;
  ban)
    [[ $# -eq 2 ]] || usage
    policy_set="$(set_name "$1")"
    validate_ipv4 "$2"
    ensure_policy
    nft add element "$TABLE_FAMILY" "$TABLE_NAME" "$policy_set" \
      "{ $2 timeout 10m }"
    ;;
  unban)
    [[ $# -eq 2 ]] || usage
    policy_set="$(set_name "$1")"
    validate_ipv4 "$2"
    check_policy
    nft delete element "$TABLE_FAMILY" "$TABLE_NAME" "$policy_set" \
      "{ $2 }" 2>/dev/null || check_policy
    ;;
  *)
    usage
    ;;
esac
