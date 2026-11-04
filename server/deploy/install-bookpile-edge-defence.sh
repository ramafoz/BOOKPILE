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
installation_started='false'
installation_accepted='false'
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

cleanup_failed_installation() {
  local rc=$?
  trap - EXIT
  if [[ "$installation_started" == 'true' && "$installation_accepted" != 'true' ]]; then
    systemctl disable --now fail2ban.service >/dev/null 2>&1 || true
  fi
  exit "$rc"
}
trap cleanup_failed_installation EXIT

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

assert_only_approved_jails() {
  local jail
  local -a jails=()
  mapfile -t jails < <(
    fail2ban-client -d 2>/dev/null |
      sed -n "s/^\['add', '\([^']*\)',.*$/\1/p" |
      sort -u
  )
  [[ ${#jails[@]} -eq 2 ]] || {
    printf 'Expected exactly two approved jails; found: %s\n' "${jails[*]:-(none)}" >&2
    exit 1
  }
  for jail in "${jails[@]}"; do
    [[ "$jail" == "$LIVE_JAIL" || "$jail" == "$READY_JAIL" ]] || {
      echo "Unapproved enabled jail: $jail" >&2
      exit 1
    }
  done
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
    if dpkg-query -W -f='${db:Status-Status}' fail2ban 2>/dev/null | grep -q '^installed$'; then
      echo 'Fail2ban is already installed; review existing host policy manually instead of overwriting it.' >&2
      exit 1
    fi
    export DEBIAN_FRONTEND=noninteractive
    systemctl mask --runtime fail2ban.service
    apt-get update
    apt-get install -y --no-install-recommends fail2ban nftables
    firewall_before="$(nft -j list ruleset | sha256sum | cut -d' ' -f1)"
    install -o root -g root -m 0644 "$source_root/fail2ban/fail2ban.d/bookpile.local" "$CONFIG_ROOT/fail2ban.d/bookpile.local"
    install -o root -g root -m 0644 "$source_root/fail2ban/filter.d/bookpile-health-live.conf" "$CONFIG_ROOT/filter.d/bookpile-health-live.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/filter.d/bookpile-health-ready.conf" "$CONFIG_ROOT/filter.d/bookpile-health-ready.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/action.d/bookpile-observe.conf" "$CONFIG_ROOT/action.d/bookpile-observe.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/jail.d/bookpile-disable-packaged.local" "$CONFIG_ROOT/jail.d/bookpile-disable-packaged.local"
    install -o root -g root -m 0644 "$source_root/fail2ban/jail.d/bookpile-health.conf" "$CONFIG_ROOT/jail.d/bookpile-health.conf"
    install -o root -g root -m 0644 "$source_root/fail2ban/jail.d/bookpile-observe.local" "$CONFIG_ROOT/jail.d/bookpile-observe.local"
    bash "$source_root/fail2ban/tests/test-health-filters.sh"
    fail2ban-client -t
    assert_only_approved_jails
    systemctl unmask --runtime fail2ban.service
    installation_started='true'
    systemctl enable --now fail2ban.service
    fail2ban-client reload
    fail2ban-client status "$LIVE_JAIL" >/dev/null
    fail2ban-client status "$READY_JAIL" >/dev/null
    assert_no_firewall_policy
    firewall_after="$(nft -j list ruleset | sha256sum | cut -d' ' -f1)"
    [[ "$firewall_before" == "$firewall_after" ]] || {
      echo 'Firewall rules changed during observation-only installation.' >&2
      exit 1
    }
    installation_accepted='true'
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
    assert_only_approved_jails
    [[ -f /var/lib/fail2ban/fail2ban.sqlite3 ]]
    assert_no_firewall_policy
    status_json
    ;;
esac
