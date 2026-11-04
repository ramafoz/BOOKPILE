#!/usr/bin/env bash
set -Eeuo pipefail

readonly LIVE_JAIL='bookpile-health-live-observe'
readonly READY_JAIL='bookpile-health-ready-observe'
readonly CONFIRMATION='STAGING-D6-OBSERVE-INSTALL'
readonly LOG_PATH='/var/log/bookpile/defensive-events.log'
readonly CONFIG_ROOT='/etc/fail2ban'

usage() {
  echo "Usage: $0 --check | --install-observe --confirm ${CONFIRMATION} | --disable-observe" >&2
  exit 2
}

mode="${1:-}"
shift || true
confirmation=''
if [[ "${1:-}" == '--confirm' ]]; then
  confirmation="${2:-}"
  shift 2 || true
fi
[[ $# -eq 0 ]] || usage
[[ "$mode" == '--check' || "$mode" == '--install-observe' || "$mode" == '--disable-observe' ]] || usage

if [[ "$mode" == '--install-observe' && "$confirmation" != "$CONFIRMATION" ]]; then
  echo "Installation requires --confirm ${CONFIRMATION}." >&2
  exit 2
fi
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }

source_root="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
validator="$source_root/validate-caddy-defensive-log.py"

check_host() {
  source /etc/os-release
  [[ "${ID:-}" == ubuntu && "${VERSION_ID:-}" == '24.04' ]] || {
    echo 'D6 observation is approved only for Ubuntu 24.04.' >&2
    exit 1
  }
  if ip -6 -o addr show scope global 2>/dev/null | grep -q .; then
    echo 'Public/global IPv6 is present; equivalent IPv6 policy must be reviewed first.' >&2
    exit 1
  fi
}

assert_no_firewall_policy() {
  nft list table inet bookpile >/dev/null 2>&1 && {
    echo 'Unexpected BOOKPILE nftables table in observation mode.' >&2
    exit 1
  }
  return 0
}

check_log() {
  [[ -f "$LOG_PATH" && ! -L "$LOG_PATH" && -r "$LOG_PATH" ]] || {
    echo "Missing, unreadable, or unsafe defensive log: $LOG_PATH" >&2
    exit 1
  }
  python3 "$validator" "$LOG_PATH" >/dev/null
}

status_json() {
  local live='inactive' ready='inactive' persistent='false'
  fail2ban-client status "$LIVE_JAIL" >/dev/null 2>&1 && live='active'
  fail2ban-client status "$READY_JAIL" >/dev/null 2>&1 && ready='active'
  [[ -f /var/lib/fail2ban/fail2ban.sqlite3 ]] && persistent='true'
  printf '{"firewall_mutated":false,"live_observation":"%s","persistent_database":%s,"ready_observation":"%s"}\n' \
    "$live" "$persistent" "$ready"
}

case "$mode" in
  --install-observe)
    check_host
    check_log
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y --no-install-recommends fail2ban nftables
    install -o root -g root -m 0644 "$source_root/fail2ban/fail2ban.d/bookpile.local" "$CONFIG_ROOT/fail2ban.d/bookpile.local"
    install -o root -g root -m 0644 "$source_root/fail2ban/filter.d/bookpile-health-live.conf" "$CONFIG_ROOT/filter.d/bookpile-health-live.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/filter.d/bookpile-health-ready.conf" "$CONFIG_ROOT/filter.d/bookpile-health-ready.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/action.d/bookpile-observe.conf" "$CONFIG_ROOT/action.d/bookpile-observe.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/jail.d/bookpile-health.conf" "$CONFIG_ROOT/jail.d/bookpile-health.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/jail.d/bookpile-observe.local" "$CONFIG_ROOT/jail.d/bookpile-observe.local"
    "$source_root/fail2ban/tests/test-health-filters.sh"
    fail2ban-client -t
    systemctl enable --now fail2ban.service
    fail2ban-client reload
    fail2ban-client status "$LIVE_JAIL" >/dev/null
    fail2ban-client status "$READY_JAIL" >/dev/null
    assert_no_firewall_policy
    status_json
    ;;
  --disable-observe)
    if command -v fail2ban-client >/dev/null 2>&1; then
      fail2ban-client stop "$LIVE_JAIL" >/dev/null 2>&1 || true
      fail2ban-client stop "$READY_JAIL" >/dev/null 2>&1 || true
    fi
    rm -f "$CONFIG_ROOT/jail.d/bookpile-observe.local"
    systemctl is-active --quiet fail2ban.service && fail2ban-client reload || true
    status_json
    ;;
  --check)
    check_host
    check_log
    command -v fail2ban-client >/dev/null
    fail2ban-client -t
    [[ -f /var/lib/fail2ban/fail2ban.sqlite3 ]]
    assert_no_firewall_policy
    status_json
    ;;
esac
