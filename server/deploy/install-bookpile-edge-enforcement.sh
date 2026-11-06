#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_CONFIRMATION='STAGING-D6-ENFORCEMENT-POLICY'
readonly ENABLE_CONFIRMATION='STAGING-D6-ENFORCEMENT-ENABLE'
readonly CONFIG_ROOT='/etc/fail2ban'
readonly LIVE_OBSERVE='bookpile-health-live-observe'
readonly READY_OBSERVE='bookpile-health-ready-observe'
readonly LIVE_ENFORCE='bookpile-health-live-enforce'
readonly READY_ENFORCE='bookpile-health-ready-enforce'
readonly LIVE_SWITCH="$CONFIG_ROOT/jail.d/zz-bookpile-live-enforce.local"
readonly READY_SWITCH="$CONFIG_ROOT/jail.d/zz-bookpile-ready-enforce.local"

usage() {
  cat >&2 <<EOF
Usage: $0 --install-disabled --confirm ${INSTALL_CONFIRMATION}
       $0 --check | --check-disabled
       $0 --enable-live --confirm ${ENABLE_CONFIRMATION}
       $0 --enable-ready --confirm ${ENABLE_CONFIRMATION}
       $0 --disable-live | --disable-ready | --disable-all
EOF
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
case "$mode" in
  --install-disabled|--check|--check-disabled|--enable-live|--enable-ready|--disable-live|--disable-ready|--disable-all) ;;
  *) usage ;;
esac
if [[ "$mode" == '--install-disabled' && "$confirmation" != "$INSTALL_CONFIRMATION" ]]; then
  echo "Installation requires --confirm ${INSTALL_CONFIRMATION}." >&2
  exit 2
fi
if [[ ( "$mode" == '--enable-live' || "$mode" == '--enable-ready' ) && "$confirmation" != "$ENABLE_CONFIRMATION" ]]; then
  echo "Enforcement requires --confirm ${ENABLE_CONFIRMATION}." >&2
  exit 2
fi
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }

source_root="$(CDPATH= cd -- "$(dirname "$0")" && pwd)"
observation_installer="$source_root/install-bookpile-edge-defence.sh"
readonly -a STATIC_FILES=(
  'bookpile-edge-firewall.sh:/usr/local/sbin/bookpile-edge-firewall:755'
  'validate-bookpile-nftables.py:/usr/local/libexec/bookpile/validate-bookpile-nftables:755'
  'nftables/bookpile-health-enforcement.nft:/usr/local/share/bookpile/bookpile-health-enforcement.nft:644'
  'fail2ban/action.d/bookpile-nftables-live.conf:/etc/fail2ban/action.d/bookpile-nftables-live.conf:644'
  'fail2ban/action.d/bookpile-nftables-ready.conf:/etc/fail2ban/action.d/bookpile-nftables-ready.conf:644'
  'fail2ban/jail.d/bookpile-health-enforce.conf:/etc/fail2ban/jail.d/bookpile-health-enforce.conf:644'
)

wait_for_server() {
  local attempt
  for attempt in $(seq 1 30); do
    fail2ban-client ping >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo 'Fail2ban did not become ready within 30 seconds.' >&2
  return 1
}

assert_no_global_ipv6() {
  if ip -6 -o addr show scope global 2>/dev/null | grep -q .; then
    echo 'Public/global IPv6 is present; equivalent IPv6 enforcement must be reviewed first.' >&2
    exit 1
  fi
}

assert_safe_directories() {
  local directory
  for directory in /usr/local/sbin /usr/local/libexec /usr/local/share "$CONFIG_ROOT/action.d" "$CONFIG_ROOT/jail.d"; do
    [[ -d "$directory" && ! -L "$directory" ]] || {
      echo "Missing, unsafe, or symlinked policy directory: $directory" >&2
      exit 1
    }
  done
  for directory in /usr/local/libexec/bookpile /usr/local/share/bookpile; do
    if [[ -e "$directory" || -L "$directory" ]]; then
      [[ -d "$directory" && ! -L "$directory" ]] || {
        echo "Unsafe BOOKPILE policy directory: $directory" >&2
        exit 1
      }
    fi
  done
}

install_static_files() {
  local entry source destination mode
  install -d -o root -g root -m 0755 /usr/local/libexec/bookpile /usr/local/share/bookpile
  for entry in "${STATIC_FILES[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    if [[ -e "$destination" || -L "$destination" ]]; then
      [[ -f "$destination" && ! -L "$destination" ]] || {
        echo "Unsafe installed enforcement file: $destination" >&2
        exit 1
      }
      cmp --silent "$source_root/$source" "$destination" || {
        echo "Installed enforcement file differs from reviewed source: $destination" >&2
        exit 1
      }
    else
      install -o root -g root -m "$mode" "$source_root/$source" "$destination"
    fi
  done
}

assert_static_files() {
  local entry source destination mode
  for entry in "${STATIC_FILES[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Missing or unsafe enforcement file: $destination" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == "root:root $mode" ]] || {
      echo "Unsafe ownership or mode on enforcement file: $destination" >&2
      exit 1
    }
    cmp --silent "$source_root/$source" "$destination" || {
      echo "Installed enforcement file differs from reviewed source: $destination" >&2
      exit 1
    }
  done
}

assert_switch() {
  local policy="$1" switch source
  case "$policy" in
    live)
      switch="$LIVE_SWITCH"
      source="$source_root/fail2ban/jail.d/zz-bookpile-live-enforce.local"
      ;;
    ready)
      switch="$READY_SWITCH"
      source="$source_root/fail2ban/jail.d/zz-bookpile-ready-enforce.local"
      ;;
    *) usage ;;
  esac
  [[ -f "$switch" && ! -L "$switch" ]] || {
    echo "Missing or unsafe enforcement switch: $switch" >&2
    exit 1
  }
  [[ "$(stat -c '%U:%G %a' "$switch")" == 'root:root 644' ]] || {
    echo "Unsafe enforcement-switch ownership or mode: $switch" >&2
    exit 1
  }
  cmp --silent "$source" "$switch" || {
    echo "Enforcement switch differs from reviewed source: $switch" >&2
    exit 1
  }
}

assert_optional_switches() {
  [[ ! -e "$LIVE_SWITCH" && ! -L "$LIVE_SWITCH" ]] || assert_switch live
  [[ ! -e "$READY_SWITCH" && ! -L "$READY_SWITCH" ]] || assert_switch ready
}

configured_jails() {
  fail2ban-client -d 2>/dev/null |
    sed -n "s/^\['add', '\([^']*\)',.*$/\1/p" |
    sort -u
}

runtime_jails() {
  fail2ban-client status |
    sed -n 's/^`- Jail list:[[:space:]]*//p' |
    tr ',' '\n' |
    sed 's/^[[:space:]]*//;s/[[:space:]]*$//' |
    sed '/^$/d' |
    sort -u
}

expected_jails() {
  if [[ -e "$LIVE_SWITCH" || -L "$LIVE_SWITCH" ]]; then
    printf '%s\n' "$LIVE_ENFORCE"
  else
    printf '%s\n' "$LIVE_OBSERVE"
  fi
  if [[ -e "$READY_SWITCH" || -L "$READY_SWITCH" ]]; then
    printf '%s\n' "$READY_ENFORCE"
  else
    printf '%s\n' "$READY_OBSERVE"
  fi
}

assert_jails() {
  local expected configured runtime
  expected="$(expected_jails)"
  configured="$(configured_jails)"
  runtime="$(runtime_jails)"
  [[ "$configured" == "$expected" ]] || {
    printf 'Unexpected configured jail set:\n%s\n' "$configured" >&2
    exit 1
  }
  [[ "$runtime" == "$expected" ]] || {
    printf 'Unexpected runtime jail set:\n%s\n' "$runtime" >&2
    exit 1
  }
}

assert_no_policy_table() {
  nft list table inet bookpile >/dev/null 2>&1 && {
    echo 'BOOKPILE nftables policy must be absent while enforcement is disabled.' >&2
    exit 1
  }
  return 0
}

policy_status() {
  local live='observe' ready='observe' firewall='absent'
  [[ -e "$LIVE_SWITCH" ]] && live='enforce'
  [[ -e "$READY_SWITCH" ]] && ready='enforce'
  nft list table inet bookpile >/dev/null 2>&1 && firewall='active'
  printf '{"firewall":"%s","live":"%s","ready":"%s","ssh_port_matched":false}\n' \
    "$firewall" "$live" "$ready"
}

preflight() {
  assert_no_global_ipv6
  assert_safe_directories
  bash "$observation_installer" --provenance-check >/dev/null
  assert_static_files
  assert_optional_switches
  systemctl is-active --quiet fail2ban.service || {
    echo 'Fail2ban must be active.' >&2
    exit 1
  }
  fail2ban-client -t >/dev/null
}

cleanup_failed_enable() {
  local rc=$?
  trap - EXIT
  if [[ -n "${new_switch:-}" ]]; then
    rm -f "$new_switch"
    fail2ban-client reload >/dev/null 2>&1 || systemctl disable --now fail2ban.service >/dev/null 2>&1 || true
    if [[ ! -e "$LIVE_SWITCH" && ! -e "$READY_SWITCH" ]]; then
      nft delete table inet bookpile >/dev/null 2>&1 || true
    fi
  fi
  exit "$rc"
}

emergency_disable_all() {
  rm -f "$LIVE_SWITCH" "$READY_SWITCH"
  systemctl disable --now fail2ban.service >/dev/null 2>&1 || true
  nft delete table inet bookpile >/dev/null 2>&1 || true
  echo 'Enforcement disable checks failed; emergency fail-open cleanup disabled Fail2ban and removed the BOOKPILE policy.' >&2
}

disable_policy() {
  local policy="$1" switch jail
  case "$policy" in
    live) switch="$LIVE_SWITCH"; jail="$LIVE_ENFORCE" ;;
    ready) switch="$READY_SWITCH"; jail="$READY_ENFORCE" ;;
    *) usage ;;
  esac
  trap emergency_disable_all ERR
  assert_no_global_ipv6
  assert_safe_directories
  rm -f "$switch"
  fail2ban-client stop "$jail" >/dev/null 2>&1 || true
  fail2ban-client -t >/dev/null
  fail2ban-client reload
  wait_for_server
  if [[ -e "$LIVE_SWITCH" || -e "$READY_SWITCH" ]]; then
    /usr/local/sbin/bookpile-edge-firewall flush "$policy"
    /usr/local/sbin/bookpile-edge-firewall check
  else
    /usr/local/sbin/bookpile-edge-firewall destroy
  fi
  assert_static_files
  assert_optional_switches
  bash "$observation_installer" --provenance-check >/dev/null
  assert_jails
  trap - ERR
  policy_status
}

case "$mode" in
  --install-disabled)
    assert_no_global_ipv6
    assert_safe_directories
    bash "$observation_installer" --check >/dev/null
    [[ ! -e "$LIVE_SWITCH" && ! -L "$LIVE_SWITCH" && ! -e "$READY_SWITCH" && ! -L "$READY_SWITCH" ]] || {
      echo 'Refusing disabled installation while an enforcement switch exists.' >&2
      exit 1
    }
    assert_no_policy_table
    install_static_files
    assert_static_files
    bash "$observation_installer" --provenance-check >/dev/null
    fail2ban-client -t >/dev/null
    assert_jails
    assert_no_policy_table
    policy_status
    ;;
  --check-disabled)
    preflight
    [[ ! -e "$LIVE_SWITCH" && ! -L "$LIVE_SWITCH" && ! -e "$READY_SWITCH" && ! -L "$READY_SWITCH" ]] || {
      echo 'At least one enforcement policy is enabled.' >&2
      exit 1
    }
    assert_jails
    assert_no_policy_table
    policy_status
    ;;
  --check)
    preflight
    assert_jails
    if [[ -e "$LIVE_SWITCH" || -e "$READY_SWITCH" ]]; then
      /usr/local/sbin/bookpile-edge-firewall check
    else
      assert_no_policy_table
    fi
    policy_status
    ;;
  --enable-live|--enable-ready)
    preflight
    policy="${mode#--enable-}"
    case "$policy" in
      live) new_switch="$LIVE_SWITCH"; source_switch="$source_root/fail2ban/jail.d/zz-bookpile-live-enforce.local" ;;
      ready) new_switch="$READY_SWITCH"; source_switch="$source_root/fail2ban/jail.d/zz-bookpile-ready-enforce.local" ;;
      *) usage ;;
    esac
    [[ ! -e "$new_switch" && ! -L "$new_switch" ]] || {
      assert_switch "$policy"
      assert_jails
      /usr/local/sbin/bookpile-edge-firewall check
      policy_status
      exit 0
    }
    trap cleanup_failed_enable EXIT
    install -o root -g root -m 0644 "$source_switch" "$new_switch"
    fail2ban-client -t >/dev/null
    fail2ban-client reload
    wait_for_server
    assert_optional_switches
    bash "$observation_installer" --provenance-check >/dev/null
    assert_jails
    /usr/local/sbin/bookpile-edge-firewall check
    new_switch=''
    trap - EXIT
    policy_status
    ;;
  --disable-live)
    disable_policy live
    ;;
  --disable-ready)
    disable_policy ready
    ;;
  --disable-all)
    trap emergency_disable_all ERR
    rm -f "$LIVE_SWITCH" "$READY_SWITCH"
    fail2ban-client stop "$LIVE_ENFORCE" >/dev/null 2>&1 || true
    fail2ban-client stop "$READY_ENFORCE" >/dev/null 2>&1 || true
    fail2ban-client -t >/dev/null
    fail2ban-client reload
    wait_for_server
    /usr/local/sbin/bookpile-edge-firewall destroy
    preflight
    assert_jails
    assert_no_policy_table
    trap - ERR
    policy_status
    ;;
esac
