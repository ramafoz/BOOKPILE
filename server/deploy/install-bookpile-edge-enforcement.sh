#!/usr/bin/env bash
set -Eeuo pipefail

readonly INSTALL_CONFIRMATION='STAGING-D6-ENFORCEMENT-POLICY'
readonly ENABLE_CONFIRMATION='STAGING-D6-ENFORCEMENT-ENABLE'
readonly SCANNER_CONFIRMATION='STAGING-D6-SCANNER-OBSERVE'
readonly SCANNER_POLICY_CONFIRMATION='STAGING-D6-SCANNER-ENFORCEMENT-POLICY'
readonly SCANNER_ENABLE_CONFIRMATION='STAGING-D6-SCANNER-ENFORCEMENT-ENABLE'
readonly CONFIG_ROOT='/etc/fail2ban'
readonly LIVE_OBSERVE='bookpile-health-live-observe'
readonly READY_OBSERVE='bookpile-health-ready-observe'
readonly LIVE_ENFORCE='bookpile-health-live-enforce'
readonly READY_ENFORCE='bookpile-health-ready-enforce'
readonly SCANNER_OBSERVE='bookpile-scanner-observe'
readonly SCANNER_ENFORCE='bookpile-scanner-enforce'
readonly LIVE_SWITCH="$CONFIG_ROOT/jail.d/zz-bookpile-live-enforce.local"
readonly READY_SWITCH="$CONFIG_ROOT/jail.d/zz-bookpile-ready-enforce.local"
readonly SCANNER_SWITCH="$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local"
readonly SCANNER_ENFORCE_SWITCH="$CONFIG_ROOT/jail.d/zzz-bookpile-scanner-enforce.local"

usage() {
  cat >&2 <<EOF
Usage: $0 --install-disabled --confirm ${INSTALL_CONFIRMATION}
       $0 --check | --check-disabled
       $0 --enable-live --confirm ${ENABLE_CONFIRMATION}
       $0 --enable-ready --confirm ${ENABLE_CONFIRMATION}
       $0 --enable-scanner-observe --confirm ${SCANNER_CONFIRMATION}
       $0 --disable-scanner-observe
       $0 --install-scanner-enforcement-disabled --confirm ${SCANNER_POLICY_CONFIRMATION}
       $0 --enable-scanner-enforcement --confirm ${SCANNER_ENABLE_CONFIRMATION}
       $0 --disable-scanner-enforcement
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
  --install-disabled|--check|--check-disabled|--enable-live|--enable-ready) ;;
  --enable-scanner-observe|--disable-scanner-observe) ;;
  --install-scanner-enforcement-disabled|--enable-scanner-enforcement) ;;
  --disable-scanner-enforcement) ;;
  --disable-live|--disable-ready|--disable-all) ;;
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
if [[ "$mode" == '--enable-scanner-observe' && \
      "$confirmation" != "$SCANNER_CONFIRMATION" ]]; then
  echo "Scanner observation requires --confirm ${SCANNER_CONFIRMATION}." >&2
  exit 2
fi
if [[ "$mode" == '--install-scanner-enforcement-disabled' && \
      "$confirmation" != "$SCANNER_POLICY_CONFIRMATION" ]]; then
  echo "Scanner enforcement installation requires --confirm ${SCANNER_POLICY_CONFIRMATION}." >&2
  exit 2
fi
if [[ "$mode" == '--enable-scanner-enforcement' && \
      "$confirmation" != "$SCANNER_ENABLE_CONFIRMATION" ]]; then
  echo "Scanner enforcement requires --confirm ${SCANNER_ENABLE_CONFIRMATION}." >&2
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
  'fail2ban/action.d/bookpile-nftables-scanner.conf:/etc/fail2ban/action.d/bookpile-nftables-scanner.conf:644'
  'fail2ban/jail.d/bookpile-health-enforce.conf:/etc/fail2ban/jail.d/bookpile-health-enforce.conf:644'
  'fail2ban/jail.d/bookpile-scanner-enforce.conf:/etc/fail2ban/jail.d/bookpile-scanner-enforce.conf:644'
)
readonly -a SCANNER_FILES=(
  'fail2ban/filter.d/bookpile-scanner-probe.conf:/etc/fail2ban/filter.d/bookpile-scanner-probe.conf:644'
  'fail2ban/jail.d/bookpile-scanner-observe.conf:/etc/fail2ban/jail.d/bookpile-scanner-observe.conf:644'
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

wait_for_policy() {
  local attempt
  for attempt in $(seq 1 30); do
    /usr/local/sbin/bookpile-edge-firewall check >/dev/null 2>&1 && return 0
    sleep 1
  done
  echo 'BOOKPILE nftables policy did not become ready within 30 seconds.' >&2
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

assert_legacy_static_files() {
  local destination expected_hash source mode
  local -a unchanged=(
    'fail2ban/action.d/bookpile-nftables-live.conf:/etc/fail2ban/action.d/bookpile-nftables-live.conf:644'
    'fail2ban/action.d/bookpile-nftables-ready.conf:/etc/fail2ban/action.d/bookpile-nftables-ready.conf:644'
    'fail2ban/jail.d/bookpile-health-enforce.conf:/etc/fail2ban/jail.d/bookpile-health-enforce.conf:644'
  )
  local -a legacy=(
    '/usr/local/sbin/bookpile-edge-firewall:755:8b949a5bef4aab992fd2a3a35128838031bd1580e3c736ab717d87ddf164872d'
    '/usr/local/libexec/bookpile/validate-bookpile-nftables:755:8cf66a3a5e9a41d667c741f23e1e38bf379ca41d7f70e8d8d37464040c6e7283'
    '/usr/local/share/bookpile/bookpile-health-enforcement.nft:644:3fca7e7563e8119bc326f53d9697c6d52368641bdb1104026dbc0dd04473a508'
  )
  local entry

  for entry in "${unchanged[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Missing or unsafe legacy enforcement file: $destination" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == "root:root $mode" ]] || {
      echo "Unsafe ownership or mode on legacy enforcement file: $destination" >&2
      exit 1
    }
    cmp --silent "$source_root/$source" "$destination" || {
      echo "Legacy enforcement file differs from its reviewed source: $destination" >&2
      exit 1
    }
  done
  for entry in "${legacy[@]}"; do
    IFS=: read -r destination mode expected_hash <<<"$entry"
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Missing or unsafe legacy enforcement file: $destination" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == "root:root $mode" ]] || {
      echo "Unsafe ownership or mode on legacy enforcement file: $destination" >&2
      exit 1
    }
    [[ "$(sha256sum "$destination" | cut -d' ' -f1)" == "$expected_hash" ]] || {
      echo "Legacy enforcement file has an unreviewed digest: $destination" >&2
      exit 1
    }
  done
  [[ ! -e /etc/fail2ban/action.d/bookpile-nftables-scanner.conf && \
     ! -L /etc/fail2ban/action.d/bookpile-nftables-scanner.conf && \
     ! -e /etc/fail2ban/jail.d/bookpile-scanner-enforce.conf && \
     ! -L /etc/fail2ban/jail.d/bookpile-scanner-enforce.conf ]] || {
    echo 'Legacy enforcement installation contains partial scanner policy files.' >&2
    exit 1
  }
}

static_policy_generation() {
  local action='/etc/fail2ban/action.d/bookpile-nftables-scanner.conf'
  local jail='/etc/fail2ban/jail.d/bookpile-scanner-enforce.conf'
  if [[ -e "$action" || -L "$action" || -e "$jail" || -L "$jail" ]]; then
    assert_static_files
    printf 'scanner\n'
  else
    assert_legacy_static_files
    printf 'health-v1\n'
  fi
}

assert_compatible_static_files() {
  static_policy_generation >/dev/null
}

upgrade_static_files() {
  local entry source destination mode
  for entry in "${STATIC_FILES[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    install -o root -g root -m "$mode" "$source_root/$source" "$destination"
  done
}

assert_scanner_files() {
  local entry source destination mode
  for entry in "${SCANNER_FILES[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Missing or unsafe scanner-observation file: $destination" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == "root:root $mode" ]] || {
      echo "Unsafe ownership or mode on scanner-observation file: $destination" >&2
      exit 1
    }
    cmp --silent "$source_root/$source" "$destination" || {
      echo "Installed scanner-observation file differs from reviewed source: $destination" >&2
      exit 1
    }
  done
}

assert_optional_scanner_policy() {
  local any='false' entry source destination mode
  for entry in "${SCANNER_FILES[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    [[ -e "$destination" || -L "$destination" ]] && any='true'
  done
  [[ -e "$SCANNER_SWITCH" || -L "$SCANNER_SWITCH" ]] && any='true'
  if [[ "$any" == 'true' ]]; then
    assert_scanner_files
    if [[ -e "$SCANNER_SWITCH" || -L "$SCANNER_SWITCH" ]]; then
      [[ -f "$SCANNER_SWITCH" && ! -L "$SCANNER_SWITCH" ]] || {
        echo "Missing or unsafe scanner-observation switch: $SCANNER_SWITCH" >&2
        exit 1
      }
      [[ "$(stat -c '%U:%G %a' "$SCANNER_SWITCH")" == 'root:root 644' ]] || {
        echo "Unsafe scanner-observation switch ownership or mode: $SCANNER_SWITCH" >&2
        exit 1
      }
      cmp --silent \
        "$source_root/fail2ban/jail.d/zz-bookpile-scanner-observe.local" \
        "$SCANNER_SWITCH" || {
        echo "Scanner-observation switch differs from reviewed source: $SCANNER_SWITCH" >&2
        exit 1
      }
    fi
  fi
}

install_scanner_files() {
  local entry source destination mode
  for entry in "${SCANNER_FILES[@]}"; do
    IFS=: read -r source destination mode <<<"$entry"
    install -o root -g root -m "$mode" "$source_root/$source" "$destination"
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
    scanner)
      switch="$SCANNER_ENFORCE_SWITCH"
      source="$source_root/fail2ban/jail.d/zzz-bookpile-scanner-enforce.local"
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
  [[ ! -e "$SCANNER_ENFORCE_SWITCH" && ! -L "$SCANNER_ENFORCE_SWITCH" ]] || assert_switch scanner
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
  if [[ -e "$SCANNER_ENFORCE_SWITCH" || -L "$SCANNER_ENFORCE_SWITCH" ]]; then
    printf '%s\n' "$SCANNER_ENFORCE"
  elif [[ -e "$SCANNER_SWITCH" || -L "$SCANNER_SWITCH" ]]; then
    printf '%s\n' "$SCANNER_OBSERVE"
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
  local live='observe' ready='observe' scanner='inactive' firewall='absent'
  [[ -e "$LIVE_SWITCH" ]] && live='enforce'
  [[ -e "$READY_SWITCH" ]] && ready='enforce'
  [[ -e "$SCANNER_SWITCH" ]] && scanner='observe'
  [[ -e "$SCANNER_ENFORCE_SWITCH" ]] && scanner='enforce'
  nft list table inet bookpile >/dev/null 2>&1 && firewall='active'
  printf '{"firewall":"%s","live":"%s","ready":"%s","scanner":"%s","ssh_port_matched":false}\n' \
    "$firewall" "$live" "$ready" "$scanner"
}

preflight() {
  assert_no_global_ipv6
  assert_safe_directories
  bash "$observation_installer" --provenance-check >/dev/null
  assert_compatible_static_files
  assert_optional_scanner_policy
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
    if [[ ! -e "$LIVE_SWITCH" && ! -e "$READY_SWITCH" && \
          ! -e "$SCANNER_ENFORCE_SWITCH" ]]; then
      nft delete table inet bookpile >/dev/null 2>&1 || true
    fi
  fi
  exit "$rc"
}

cleanup_failed_scanner_enable() {
  local rc=$?
  trap - EXIT
  rm -f "$SCANNER_SWITCH"
  fail2ban-client stop "$SCANNER_OBSERVE" >/dev/null 2>&1 || true
  if ! fail2ban-client reload >/dev/null 2>&1; then
    emergency_disable_all
  fi
  exit "$rc"
}

cleanup_failed_scanner_policy_upgrade() {
  local rc=$?
  local rollback_ok='true'
  trap - EXIT
  if [[ -n "${migration_backup:-}" && -d "$migration_backup" && \
        ! -L "$migration_backup" ]]; then
    install -o root -g root -m 0755 \
      "$migration_backup/bookpile-edge-firewall" \
      /usr/local/sbin/bookpile-edge-firewall || rollback_ok='false'
    install -o root -g root -m 0755 \
      "$migration_backup/validate-bookpile-nftables" \
      /usr/local/libexec/bookpile/validate-bookpile-nftables || rollback_ok='false'
    install -o root -g root -m 0644 \
      "$migration_backup/bookpile-health-enforcement.nft" \
      /usr/local/share/bookpile/bookpile-health-enforcement.nft || rollback_ok='false'
    rm -f \
      /etc/fail2ban/action.d/bookpile-nftables-scanner.conf \
      /etc/fail2ban/jail.d/bookpile-scanner-enforce.conf || rollback_ok='false'
    if [[ "$rollback_ok" == 'true' ]]; then
      fail2ban-client reload >/dev/null 2>&1 || emergency_disable_all
    else
      emergency_disable_all
    fi
    find "$migration_backup" -type f -delete
    rmdir "$migration_backup" || true
  else
    emergency_disable_all
  fi
  exit "$rc"
}

emergency_disable_all() {
  systemctl disable --now fail2ban.service >/dev/null 2>&1 || true
  nft delete table inet bookpile >/dev/null 2>&1 || true
  if [[ -d "$CONFIG_ROOT" && ! -L "$CONFIG_ROOT" && \
        -d "$CONFIG_ROOT/jail.d" && ! -L "$CONFIG_ROOT/jail.d" ]]; then
    rm -f "$LIVE_SWITCH" "$READY_SWITCH" "$SCANNER_ENFORCE_SWITCH"
  else
    echo 'Unsafe Fail2ban configuration directories; enforcement switches require manual removal.' >&2
  fi
  echo 'Enforcement disable checks failed; emergency fail-open cleanup disabled Fail2ban and removed the BOOKPILE policy.' >&2
}

cleanup_failed_disable() {
  local rc=$?
  trap - EXIT
  if [[ "${disable_completed:-false}" != 'true' ]]; then
    emergency_disable_all
  fi
  exit "$rc"
}

disable_policy() {
  local policy="$1" switch jail
  case "$policy" in
    live) switch="$LIVE_SWITCH"; jail="$LIVE_ENFORCE" ;;
    ready) switch="$READY_SWITCH"; jail="$READY_ENFORCE" ;;
    scanner) switch="$SCANNER_ENFORCE_SWITCH"; jail="$SCANNER_ENFORCE" ;;
    *) usage ;;
  esac
  disable_completed='false'
  trap cleanup_failed_disable EXIT
  assert_no_global_ipv6
  assert_safe_directories
  rm -f "$switch"
  fail2ban-client stop "$jail" >/dev/null 2>&1 || true
  fail2ban-client -t >/dev/null
  fail2ban-client reload
  wait_for_server
  if [[ -e "$LIVE_SWITCH" || -e "$READY_SWITCH" || \
        -e "$SCANNER_ENFORCE_SWITCH" ]]; then
    /usr/local/sbin/bookpile-edge-firewall flush "$policy"
    /usr/local/sbin/bookpile-edge-firewall check
  else
    /usr/local/sbin/bookpile-edge-firewall destroy
  fi
  assert_compatible_static_files
  assert_optional_switches
  bash "$observation_installer" --provenance-check >/dev/null
  assert_jails
  disable_completed='true'
  trap - EXIT
  policy_status
}

case "$mode" in
  --install-disabled)
    assert_no_global_ipv6
    assert_safe_directories
    bash "$observation_installer" --check >/dev/null
    [[ ! -e "$LIVE_SWITCH" && ! -L "$LIVE_SWITCH" && \
       ! -e "$READY_SWITCH" && ! -L "$READY_SWITCH" && \
       ! -e "$SCANNER_ENFORCE_SWITCH" && ! -L "$SCANNER_ENFORCE_SWITCH" ]] || {
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
  --install-scanner-enforcement-disabled)
    assert_no_global_ipv6
    assert_safe_directories
    bash "$observation_installer" --provenance-check >/dev/null
    generation="$(static_policy_generation)"
    [[ ! -e "$LIVE_SWITCH" && ! -L "$LIVE_SWITCH" && \
       ! -e "$READY_SWITCH" && ! -L "$READY_SWITCH" && \
       ! -e "$SCANNER_ENFORCE_SWITCH" && ! -L "$SCANNER_ENFORCE_SWITCH" ]] || {
      echo 'Disable every enforcement policy before migrating the scanner policy.' >&2
      exit 1
    }
    assert_no_policy_table
    if [[ "$generation" == 'scanner' ]]; then
      fail2ban-client -t >/dev/null
      assert_jails
      policy_status
      exit 0
    fi
    migration_backup="$(mktemp -d /tmp/bookpile-scanner-policy.XXXXXX)"
    chmod 0700 "$migration_backup"
    cp -p /usr/local/sbin/bookpile-edge-firewall \
      "$migration_backup/bookpile-edge-firewall"
    cp -p /usr/local/libexec/bookpile/validate-bookpile-nftables \
      "$migration_backup/validate-bookpile-nftables"
    cp -p /usr/local/share/bookpile/bookpile-health-enforcement.nft \
      "$migration_backup/bookpile-health-enforcement.nft"
    trap cleanup_failed_scanner_policy_upgrade EXIT
    upgrade_static_files
    assert_static_files
    bash "$observation_installer" --provenance-check >/dev/null
    fail2ban-client -t >/dev/null
    fail2ban-client reload
    wait_for_server
    assert_jails
    assert_no_policy_table
    find "$migration_backup" -type f -delete
    rmdir "$migration_backup"
    migration_backup=''
    trap - EXIT
    policy_status
    ;;
  --check-disabled)
    preflight
    [[ ! -e "$LIVE_SWITCH" && ! -L "$LIVE_SWITCH" && \
       ! -e "$READY_SWITCH" && ! -L "$READY_SWITCH" && \
       ! -e "$SCANNER_ENFORCE_SWITCH" && ! -L "$SCANNER_ENFORCE_SWITCH" ]] || {
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
    if [[ -e "$LIVE_SWITCH" || -e "$READY_SWITCH" || \
          -e "$SCANNER_ENFORCE_SWITCH" ]]; then
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
    wait_for_policy
    new_switch=''
    trap - EXIT
    policy_status
    ;;
  --enable-scanner-observe)
    preflight
    [[ ! -e "$SCANNER_ENFORCE_SWITCH" && ! -L "$SCANNER_ENFORCE_SWITCH" ]] || {
      echo 'Disable scanner enforcement before enabling scanner observation.' >&2
      exit 1
    }
    if [[ -e "$SCANNER_SWITCH" || -L "$SCANNER_SWITCH" ]]; then
      assert_optional_scanner_policy
      assert_jails
      fail2ban-client status "$SCANNER_OBSERVE" >/dev/null
      policy_status
      exit 0
    fi
    firewall_before="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    trap cleanup_failed_scanner_enable EXIT
    install_scanner_files
    install -o root -g root -m 0644 \
      "$source_root/fail2ban/jail.d/zz-bookpile-scanner-observe.local" \
      "$SCANNER_SWITCH"
    bash "$source_root/fail2ban/tests/test-health-filters.sh" >/dev/null
    fail2ban-client -t >/dev/null
    assert_optional_scanner_policy
    bash "$observation_installer" --provenance-check >/dev/null
    fail2ban-client reload
    wait_for_server
    assert_jails
    fail2ban-client status "$SCANNER_OBSERVE" >/dev/null
    firewall_after="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    [[ "$firewall_before" == "$firewall_after" ]] || {
      echo 'Firewall rules changed while enabling scanner observation.' >&2
      exit 1
    }
    trap - EXIT
    policy_status
    ;;
  --disable-scanner-observe)
    preflight
    [[ ! -e "$SCANNER_ENFORCE_SWITCH" && ! -L "$SCANNER_ENFORCE_SWITCH" ]] || {
      echo 'Disable scanner enforcement before disabling scanner observation.' >&2
      exit 1
    }
    [[ -e "$SCANNER_SWITCH" && ! -L "$SCANNER_SWITCH" ]] || {
      echo 'Scanner observation is not enabled.' >&2
      exit 1
    }
    firewall_before="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    rm -f "$SCANNER_SWITCH"
    fail2ban-client stop "$SCANNER_OBSERVE" >/dev/null 2>&1 || true
    fail2ban-client -t >/dev/null
    fail2ban-client reload
    wait_for_server
    assert_optional_scanner_policy
    bash "$observation_installer" --provenance-check >/dev/null
    assert_jails
    firewall_after="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    [[ "$firewall_before" == "$firewall_after" ]] || {
      emergency_disable_all
      exit 1
    }
    policy_status
    ;;
  --enable-scanner-enforcement)
    preflight
    assert_static_files
    [[ -e "$SCANNER_SWITCH" && ! -L "$SCANNER_SWITCH" ]] || {
      echo 'Scanner observation must remain installed before enforcement is enabled.' >&2
      exit 1
    }
    if [[ -e "$SCANNER_ENFORCE_SWITCH" || -L "$SCANNER_ENFORCE_SWITCH" ]]; then
      assert_switch scanner
      assert_jails
      /usr/local/sbin/bookpile-edge-firewall check
      policy_status
      exit 0
    fi
    new_switch="$SCANNER_ENFORCE_SWITCH"
    trap cleanup_failed_enable EXIT
    install -o root -g root -m 0644 \
      "$source_root/fail2ban/jail.d/zzz-bookpile-scanner-enforce.local" \
      "$new_switch"
    fail2ban-client -t >/dev/null
    fail2ban-client reload
    wait_for_server
    assert_optional_switches
    bash "$observation_installer" --provenance-check >/dev/null
    assert_jails
    wait_for_policy
    new_switch=''
    trap - EXIT
    policy_status
    ;;
  --disable-scanner-enforcement)
    disable_policy scanner
    ;;
  --disable-live)
    disable_policy live
    ;;
  --disable-ready)
    disable_policy ready
    ;;
  --disable-all)
    disable_completed='false'
    trap cleanup_failed_disable EXIT
    rm -f "$LIVE_SWITCH" "$READY_SWITCH" "$SCANNER_ENFORCE_SWITCH"
    fail2ban-client stop "$LIVE_ENFORCE" >/dev/null 2>&1 || true
    fail2ban-client stop "$READY_ENFORCE" >/dev/null 2>&1 || true
    fail2ban-client stop "$SCANNER_ENFORCE" >/dev/null 2>&1 || true
    fail2ban-client -t >/dev/null
    fail2ban-client reload
    wait_for_server
    /usr/local/sbin/bookpile-edge-firewall destroy
    preflight
    assert_jails
    assert_no_policy_table
    disable_completed='true'
    trap - EXIT
    policy_status
    ;;
esac
