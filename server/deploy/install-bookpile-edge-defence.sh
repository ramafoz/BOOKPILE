#!/usr/bin/env bash
set -Eeuo pipefail

readonly LIVE_JAIL='bookpile-health-live-observe'
readonly READY_JAIL='bookpile-health-ready-observe'
readonly CONFIRMATION='STAGING-D6-OBSERVE-INSTALL'
readonly LOG_PATH='/var/log/bookpile/defensive-events.log'
readonly CONFIG_ROOT='/etc/fail2ban'

usage() {
  echo "Usage: $0 --check | --install-observe --confirm ${CONFIRMATION} | --resume-observe --confirm ${CONFIRMATION} | --disable-observe" >&2
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
[[ "$mode" == '--check' || "$mode" == '--install-observe' || "$mode" == '--resume-observe' || "$mode" == '--disable-observe' ]] || usage

if [[ ( "$mode" == '--install-observe' || "$mode" == '--resume-observe' ) && "$confirmation" != "$CONFIRMATION" ]]; then
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
readonly -a MANAGED_FILES=(
  'fail2ban/fail2ban.d/bookpile.local:fail2ban.d/bookpile.local'
  'fail2ban/filter.d/bookpile-health-live.conf:filter.d/bookpile-health-live.conf'
  'fail2ban/filter.d/bookpile-health-ready.conf:filter.d/bookpile-health-ready.conf'
  'fail2ban/action.d/bookpile-observe.conf:action.d/bookpile-observe.conf'
  'fail2ban/jail.d/bookpile-disable-packaged.local:jail.d/bookpile-disable-packaged.local'
  'fail2ban/jail.d/bookpile-health.conf:jail.d/bookpile-health.conf'
  'fail2ban/jail.d/bookpile-observe.local:jail.d/bookpile-observe.local'
)

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

install_managed_files() {
  local pair source_relative destination_relative
  for pair in "${MANAGED_FILES[@]}"; do
    source_relative="${pair%%:*}"
    destination_relative="${pair#*:}"
    install -o root -g root -m 0644 \
      "$source_root/$source_relative" \
      "$CONFIG_ROOT/$destination_relative"
  done
}

assert_managed_files_match() {
  local pair source_relative destination_relative
  for pair in "${MANAGED_FILES[@]}"; do
    source_relative="${pair%%:*}"
    destination_relative="${pair#*:}"
    cmp --silent \
      "$source_root/$source_relative" \
      "$CONFIG_ROOT/$destination_relative" || {
      echo "Installed Fail2ban policy differs from the reviewed source: $destination_relative" >&2
      exit 1
    }
  done
}

wait_for_server() {
  local attempt
  for attempt in $(seq 1 30); do
    if fail2ban-client ping >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo 'Fail2ban did not become ready within 30 seconds.' >&2
  journalctl -u fail2ban.service --since '2 minutes ago' --no-pager -l >&2 || true
  return 1
}

activate_observation() {
  local firewall_before firewall_after
  firewall_before="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
  bash "$source_root/fail2ban/tests/test-health-filters.sh"
  fail2ban-client -t
  assert_only_approved_jails
  systemctl unmask --runtime fail2ban.service
  installation_started='true'
  systemctl enable --now fail2ban.service
  wait_for_server
  fail2ban-client reload
  wait_for_server
  fail2ban-client status "$LIVE_JAIL" >/dev/null
  fail2ban-client status "$READY_JAIL" >/dev/null
  assert_no_firewall_policy
  firewall_after="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
  [[ "$firewall_before" == "$firewall_after" ]] || {
    echo 'Firewall rules changed during observation-only installation.' >&2
    exit 1
  }
  installation_accepted='true'
  status_json
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
    install_managed_files
    activate_observation
    ;;
  --resume-observe)
    check_host
    check_log
    dpkg-query -W -f='${db:Status-Status}' fail2ban 2>/dev/null | grep -q '^installed$' || {
      echo 'Fail2ban is not installed; use --install-observe.' >&2
      exit 1
    }
    systemctl is-active --quiet fail2ban.service && {
      echo 'Fail2ban is already active; use --check instead of resuming.' >&2
      exit 1
    }
    assert_managed_files_match
    activate_observation
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
