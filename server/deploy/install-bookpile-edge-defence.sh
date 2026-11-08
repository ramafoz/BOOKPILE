#!/usr/bin/env bash
set -Eeuo pipefail

readonly LIVE_JAIL='bookpile-health-live-observe'
readonly READY_JAIL='bookpile-health-ready-observe'
readonly SCANNER_JAIL='bookpile-scanner-observe'
readonly CONFIRMATION='STAGING-D6-OBSERVE-INSTALL'
readonly LOG_PATH='/var/log/bookpile/defensive-events.log'
readonly CONFIG_ROOT='/etc/fail2ban'

usage() {
  echo "Usage: $0 --check | --provenance-check | --install-observe --confirm ${CONFIRMATION} | --resume-observe --confirm ${CONFIRMATION} | --upgrade-observe --confirm ${CONFIRMATION} | --enable-observe --confirm ${CONFIRMATION} | --disable-observe" >&2
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
[[ "$mode" == '--check' || "$mode" == '--provenance-check' || "$mode" == '--install-observe' || "$mode" == '--resume-observe' || "$mode" == '--upgrade-observe' || "$mode" == '--enable-observe' || "$mode" == '--disable-observe' ]] || usage

if [[ ( "$mode" == '--install-observe' || "$mode" == '--resume-observe' || "$mode" == '--upgrade-observe' || "$mode" == '--enable-observe' ) && "$confirmation" != "$CONFIRMATION" ]]; then
  echo "Installation requires --confirm ${CONFIRMATION}." >&2
  exit 2
fi
[[ $EUID -eq 0 ]] || { echo 'Run as root.' >&2; exit 1; }

cleanup_failed_installation() {
  local rc=$?
  local cleanup_ok='true'
  trap - EXIT
  if [[ "$installation_started" == 'true' && "$installation_accepted" != 'true' ]]; then
    if [[ "$mode" == '--enable-observe' ]]; then
      rm -f \
        "$CONFIG_ROOT/jail.d/bookpile-observe.local" \
        "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local"
      if systemctl is-active --quiet fail2ban.service && \
         fail2ban-client reload >/dev/null 2>&1; then
        exit "$rc"
      fi
    elif [[ "$mode" == '--disable-observe' ]]; then
      systemctl disable --now fail2ban.service >/dev/null 2>&1 || cleanup_ok='false'
      if [[ -d "$CONFIG_ROOT" && ! -L "$CONFIG_ROOT" && \
            -d "$CONFIG_ROOT/jail.d" && ! -L "$CONFIG_ROOT/jail.d" ]]; then
        rm -f \
          "$CONFIG_ROOT/jail.d/bookpile-observe.local" \
          "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local" || cleanup_ok='false'
      else
        cleanup_ok='false'
      fi
      if [[ "$cleanup_ok" == 'true' ]]; then
        echo 'Disable acceptance checks failed; emergency fail-open cleanup stopped Fail2ban and removed the observation enable override.' >&2
      else
        echo 'Disable acceptance checks failed and emergency cleanup could not fully verify the disabled state; inspect the stopped service and configuration before restarting Fail2ban.' >&2
      fi
      exit "$rc"
    fi
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
  local expected_count=2
  scanner_observation_enabled && expected_count=3
  [[ ${#jails[@]} -eq $expected_count ]] || {
    printf 'Expected exactly %s approved jails; found: %s\n' \
      "$expected_count" "${jails[*]:-(none)}" >&2
    exit 1
  }
  for jail in "${jails[@]}"; do
    [[ "$jail" == "$LIVE_JAIL" || "$jail" == "$READY_JAIL" || \
       ( "$jail" == "$SCANNER_JAIL" && $expected_count -eq 3 ) ]] || {
      echo "Unapproved enabled jail: $jail" >&2
      exit 1
    }
  done
}

scanner_policy_installed() {
  [[ -f "$CONFIG_ROOT/filter.d/bookpile-scanner-probe.conf" && \
     ! -L "$CONFIG_ROOT/filter.d/bookpile-scanner-probe.conf" && \
     -f "$CONFIG_ROOT/jail.d/bookpile-scanner-observe.conf" && \
     ! -L "$CONFIG_ROOT/jail.d/bookpile-scanner-observe.conf" ]]
}

scanner_observation_enabled() {
  scanner_policy_installed && \
    [[ -f "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local" && \
       ! -L "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local" ]]
}

expected_observation_jail_count() {
  scanner_observation_enabled && printf '3\n' || printf '2\n'
}

assert_no_enabled_jails() {
  local -a jails=()
  mapfile -t jails < <(
    fail2ban-client -d 2>/dev/null |
      sed -n "s/^\['add', '\([^']*\)',.*$/\1/p" |
      sort -u
  )
  [[ ${#jails[@]} -eq 0 ]] || {
    printf 'Expected no enabled jails; found: %s\n' "${jails[*]}" >&2
    exit 1
  }
}

assert_runtime_jail_count() {
  local expected="$1"
  local actual
  actual="$({ fail2ban-client status || true; } | sed -n 's/^[^:]*Number of jail:[[:space:]]*//p')"
  [[ "$actual" == "$expected" ]] || {
    printf 'Expected %s active jails; found: %s\n' "$expected" "${actual:-(unknown)}" >&2
    exit 1
  }
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
  local allow_missing_enable="${1:-false}"
  local allow_legacy_action="${2:-false}"
  local pair source_relative destination_relative
  local destination
  for pair in "${MANAGED_FILES[@]}"; do
    source_relative="${pair%%:*}"
    destination_relative="${pair#*:}"
    destination="$CONFIG_ROOT/$destination_relative"
    if [[ "$allow_missing_enable" == 'true' && \
          "$destination_relative" == 'jail.d/bookpile-observe.local' && \
          ! -e "$destination" && ! -L "$destination" ]]; then
      continue
    fi
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Installed Fail2ban policy is missing, non-regular, or a symlink: $destination_relative" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == 'root:root 644' ]] || {
      echo "Installed Fail2ban policy has unsafe ownership or mode: $destination_relative" >&2
      exit 1
    }
    if ! cmp --silent "$source_root/$source_relative" "$destination"; then
      if [[ "$allow_legacy_action" == 'true' && \
            "$destination_relative" == 'action.d/bookpile-observe.conf' ]] && \
         cmp --silent \
           "$source_root/fail2ban/migrations/bookpile-observe-v1.conf" \
           "$destination"; then
        continue
      fi
      echo "Installed Fail2ban policy differs from the reviewed source: $destination_relative" >&2
      exit 1
    fi
  done
}

assert_optional_scanner_files_match() {
  local any='false' pair source_relative destination_relative destination
  local -a scanner_files=(
    'fail2ban/filter.d/bookpile-scanner-probe.conf:filter.d/bookpile-scanner-probe.conf'
    'fail2ban/jail.d/bookpile-scanner-observe.conf:jail.d/bookpile-scanner-observe.conf'
  )
  for pair in "${scanner_files[@]}"; do
    destination_relative="${pair#*:}"
    destination="$CONFIG_ROOT/$destination_relative"
    [[ -e "$destination" || -L "$destination" ]] && any='true'
  done
  [[ -e "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local" || \
     -L "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local" ]] && any='true'
  [[ "$any" == 'true' ]] || return 0

  for pair in "${scanner_files[@]}"; do
    source_relative="${pair%%:*}"
    destination_relative="${pair#*:}"
    destination="$CONFIG_ROOT/$destination_relative"
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Installed scanner policy is missing, non-regular, or a symlink: $destination_relative" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == 'root:root 644' ]] || {
      echo "Installed scanner policy has unsafe ownership or mode: $destination_relative" >&2
      exit 1
    }
    cmp --silent "$source_root/$source_relative" "$destination" || {
      echo "Installed scanner policy differs from reviewed source: $destination_relative" >&2
      exit 1
    }
  done

  destination_relative='jail.d/zz-bookpile-scanner-observe.local'
  destination="$CONFIG_ROOT/$destination_relative"
  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Installed scanner switch is non-regular or a symlink: $destination_relative" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == 'root:root 644' ]] || {
      echo "Installed scanner switch has unsafe ownership or mode: $destination_relative" >&2
      exit 1
    }
    cmp --silent \
      "$source_root/fail2ban/$destination_relative" \
      "$destination" || {
      echo "Installed scanner switch differs from reviewed source: $destination_relative" >&2
      exit 1
    }
  fi
}

assert_optional_scanner_enforcement_files_match() {
  local any='false' pair source_relative destination_relative destination
  local -a files=(
    'fail2ban/action.d/bookpile-nftables-scanner.conf:action.d/bookpile-nftables-scanner.conf'
    'fail2ban/jail.d/bookpile-scanner-enforce.conf:jail.d/bookpile-scanner-enforce.conf'
  )
  for pair in "${files[@]}"; do
    destination_relative="${pair#*:}"
    destination="$CONFIG_ROOT/$destination_relative"
    [[ -e "$destination" || -L "$destination" ]] && any='true'
  done
  [[ -e "$CONFIG_ROOT/jail.d/zzz-bookpile-scanner-enforce.local" || \
     -L "$CONFIG_ROOT/jail.d/zzz-bookpile-scanner-enforce.local" ]] && any='true'
  [[ "$any" == 'true' ]] || return 0

  for pair in "${files[@]}"; do
    source_relative="${pair%%:*}"
    destination_relative="${pair#*:}"
    destination="$CONFIG_ROOT/$destination_relative"
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Installed scanner enforcement policy is missing or unsafe: $destination_relative" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == 'root:root 644' ]] || {
      echo "Installed scanner enforcement policy has unsafe ownership or mode: $destination_relative" >&2
      exit 1
    }
    cmp --silent "$source_root/$source_relative" "$destination" || {
      echo "Installed scanner enforcement policy differs from reviewed source: $destination_relative" >&2
      exit 1
    }
  done

  destination_relative='jail.d/zzz-bookpile-scanner-enforce.local'
  destination="$CONFIG_ROOT/$destination_relative"
  if [[ -e "$destination" || -L "$destination" ]]; then
    [[ -f "$destination" && ! -L "$destination" ]] || {
      echo "Installed scanner enforcement switch is unsafe: $destination_relative" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$destination")" == 'root:root 644' ]] || {
      echo "Installed scanner enforcement switch has unsafe ownership or mode: $destination_relative" >&2
      exit 1
    }
    cmp --silent "$source_root/fail2ban/$destination_relative" "$destination" || {
      echo "Installed scanner enforcement switch differs from reviewed source: $destination_relative" >&2
      exit 1
    }
  fi
}

assert_no_unreviewed_overrides() {
  local directory file package_file package_owned
  local package_verification
  local -a package_files=()
  local -a allowed_local_files=(
    "$CONFIG_ROOT/fail2ban.d/bookpile.local"
    "$CONFIG_ROOT/jail.d/bookpile-disable-packaged.local"
    "$CONFIG_ROOT/jail.d/bookpile-observe.local"
    "$CONFIG_ROOT/jail.d/zz-bookpile-live-enforce.local"
    "$CONFIG_ROOT/jail.d/zz-bookpile-ready-enforce.local"
    "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local"
    "$CONFIG_ROOT/jail.d/zzz-bookpile-scanner-enforce.local"
  )
  local allowed allowed_file

  assert_optional_scanner_files_match
  assert_optional_scanner_enforcement_files_match

  for directory in \
    "$CONFIG_ROOT" \
    "$CONFIG_ROOT/action.d" \
    "$CONFIG_ROOT/fail2ban.d" \
    "$CONFIG_ROOT/filter.d" \
    "$CONFIG_ROOT/jail.d"; do
    [[ -d "$directory" && ! -L "$directory" ]] || {
      echo "Fail2ban configuration directory is missing, non-directory, or a symlink: $directory" >&2
      exit 1
    }
    [[ "$(stat -c '%U:%G %a' "$directory")" == 'root:root 755' ]] || {
      echo "Fail2ban configuration directory has unsafe ownership or mode: $directory" >&2
      exit 1
    }
  done
  file="$(find "$CONFIG_ROOT" -type l -print -quit)"
  [[ -z "$file" ]] || {
    echo "Symlink is forbidden in the Fail2ban configuration tree: $file" >&2
    exit 1
  }

  package_verification="$(dpkg --verify fail2ban || true)"
  [[ -z "$package_verification" ]] || {
    echo 'The packaged Fail2ban configuration has been modified:' >&2
    printf '%s\n' "$package_verification" >&2
    exit 1
  }
  mapfile -t package_files < <(dpkg-query -L fail2ban)

  while IFS= read -r -d '' file; do
    allowed='false'
    for allowed_file in "${allowed_local_files[@]}"; do
      if [[ "$file" == "$allowed_file" ]]; then
        allowed='true'
        break
      fi
    done
    [[ "$allowed" == 'true' ]] || {
      echo "Unreviewed Fail2ban .local override: $file" >&2
      exit 1
    }
  done < <(find "$CONFIG_ROOT" \( -type f -o -type l \) -name '*.local' -print0)

  for file in \
    "$CONFIG_ROOT/action.d/bookpile-observe.d" \
    "$CONFIG_ROOT/action.d/bookpile-nftables-live.d" \
    "$CONFIG_ROOT/action.d/bookpile-nftables-ready.d" \
    "$CONFIG_ROOT/action.d/bookpile-nftables-scanner.d" \
    "$CONFIG_ROOT/filter.d/bookpile-health-live.d" \
    "$CONFIG_ROOT/filter.d/bookpile-health-ready.d" \
    "$CONFIG_ROOT/filter.d/bookpile-scanner-probe.d"; do
    [[ ! -e "$file" && ! -L "$file" ]] || {
      echo "Unreviewed BOOKPILE component drop-in directory: $file" >&2
      exit 1
    }
  done

  while IFS= read -r -d '' file; do
    [[ "$file" == "$CONFIG_ROOT/fail2ban.d/bookpile.local" || \
       "$file" == "$CONFIG_ROOT/jail.d/bookpile-health.conf" || \
       "$file" == "$CONFIG_ROOT/jail.d/bookpile-health-enforce.conf" || \
       "$file" == "$CONFIG_ROOT/jail.d/bookpile-scanner-observe.conf" || \
       "$file" == "$CONFIG_ROOT/jail.d/bookpile-scanner-enforce.conf" || \
       "$file" == "$CONFIG_ROOT/jail.d/bookpile-disable-packaged.local" || \
       "$file" == "$CONFIG_ROOT/jail.d/bookpile-observe.local" || \
       "$file" == "$CONFIG_ROOT/jail.d/zz-bookpile-live-enforce.local" || \
       "$file" == "$CONFIG_ROOT/jail.d/zz-bookpile-ready-enforce.local" || \
       "$file" == "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local" || \
       "$file" == "$CONFIG_ROOT/jail.d/zzz-bookpile-scanner-enforce.local" ]] && continue
    package_owned='false'
    for package_file in "${package_files[@]}"; do
      if [[ "$file" == "$package_file" ]]; then
        package_owned='true'
        break
      fi
    done
    if [[ "$package_owned" != 'true' ]]; then
      echo "Unreviewed non-package jail configuration: $file" >&2
      exit 1
    fi
  done < <(
    find "$CONFIG_ROOT/fail2ban.d" -maxdepth 1 \( -type f -o -type l \) \
      \( -name '*.conf' -o -name '*.local' \) -print0
    find "$CONFIG_ROOT" -maxdepth 1 \( -type f -o -type l \) \
      \( -name 'jail.conf' -o -name 'jail.local' \) -print0
    find "$CONFIG_ROOT/jail.d" -maxdepth 1 \( -type f -o -type l \) \
      \( -name '*.conf' -o -name '*.local' \) -print0
  )

  for file in \
    "$CONFIG_ROOT/action.d/bookpile-observe.local" \
    "$CONFIG_ROOT/action.d/bookpile-nftables-live.local" \
    "$CONFIG_ROOT/action.d/bookpile-nftables-ready.local" \
    "$CONFIG_ROOT/action.d/bookpile-nftables-scanner.local" \
    "$CONFIG_ROOT/filter.d/bookpile-health-live.local" \
    "$CONFIG_ROOT/filter.d/bookpile-health-ready.local" \
    "$CONFIG_ROOT/filter.d/bookpile-scanner-probe.local"; do
    [[ ! -e "$file" && ! -L "$file" ]] || {
      echo "Unreviewed BOOKPILE component override: $file" >&2
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
  assert_no_unreviewed_overrides
  assert_only_approved_jails
  systemctl unmask --runtime fail2ban.service
  installation_started='true'
  systemctl enable --now fail2ban.service
  wait_for_server
  fail2ban-client reload
  wait_for_server
  assert_runtime_jail_count "$(expected_observation_jail_count)"
  fail2ban-client status "$LIVE_JAIL" >/dev/null
  fail2ban-client status "$READY_JAIL" >/dev/null
  scanner_observation_enabled && fail2ban-client status "$SCANNER_JAIL" >/dev/null
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
  local live='inactive' ready='inactive' scanner='inactive' persistent='false'
  fail2ban-client status "$LIVE_JAIL" >/dev/null 2>&1 && live='active'
  fail2ban-client status "$READY_JAIL" >/dev/null 2>&1 && ready='active'
  fail2ban-client status "$SCANNER_JAIL" >/dev/null 2>&1 && scanner='active'
  [[ -f /var/lib/fail2ban/fail2ban.sqlite3 ]] && persistent='true'
  printf '{"firewall_mutated":false,"live_observation":"%s","persistent_database":%s,"ready_observation":"%s","scanner_observation":"%s"}\n' \
    "$live" "$persistent" "$ready" "$scanner"
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
  --upgrade-observe)
    check_host
    check_log
    dpkg-query -W -f='${db:Status-Status}' fail2ban 2>/dev/null | grep -q '^installed$' || {
      echo 'Fail2ban is not installed; use --install-observe.' >&2
      exit 1
    }
    systemctl is-active --quiet fail2ban.service || {
      echo 'Fail2ban must be active before upgrading observation policy.' >&2
      exit 1
    }
    assert_managed_files_match false true
    assert_no_unreviewed_overrides
    fail2ban-client -t
    assert_only_approved_jails
    assert_runtime_jail_count "$(expected_observation_jail_count)"
    firewall_before="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    installation_started='true'
    install -o root -g root -m 0644 \
      "$source_root/fail2ban/action.d/bookpile-observe.conf" \
      "$CONFIG_ROOT/action.d/bookpile-observe.conf"
    fail2ban-client -t
    assert_managed_files_match
    assert_no_unreviewed_overrides
    assert_only_approved_jails
    fail2ban-client reload
    wait_for_server
    assert_runtime_jail_count "$(expected_observation_jail_count)"
    fail2ban-client status "$LIVE_JAIL" >/dev/null
    fail2ban-client status "$READY_JAIL" >/dev/null
    scanner_observation_enabled && fail2ban-client status "$SCANNER_JAIL" >/dev/null
    assert_no_firewall_policy
    firewall_after="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    [[ "$firewall_before" == "$firewall_after" ]] || {
      echo 'Firewall rules changed while upgrading observation.' >&2
      exit 1
    }
    installation_accepted='true'
    status_json
    ;;
  --enable-observe)
    check_host
    check_log
    dpkg-query -W -f='${db:Status-Status}' fail2ban 2>/dev/null | grep -q '^installed$' || {
      echo 'Fail2ban is not installed; use --install-observe.' >&2
      exit 1
    }
    assert_managed_files_match true
    assert_no_unreviewed_overrides
    fail2ban-client -t
    assert_no_enabled_jails
    if systemctl is-active --quiet fail2ban.service; then
      assert_runtime_jail_count 0
    fi
    firewall_before="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    installation_started='true'
    install -o root -g root -m 0644 \
      "$source_root/fail2ban/jail.d/bookpile-observe.local" \
      "$CONFIG_ROOT/jail.d/bookpile-observe.local"
    if scanner_policy_installed; then
      install -o root -g root -m 0644 \
        "$source_root/fail2ban/jail.d/zz-bookpile-scanner-observe.local" \
        "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local"
    fi
    fail2ban-client -t
    assert_no_unreviewed_overrides
    assert_only_approved_jails
    if systemctl is-active --quiet fail2ban.service; then
      fail2ban-client reload
    else
      systemctl enable --now fail2ban.service
    fi
    wait_for_server
    assert_runtime_jail_count "$(expected_observation_jail_count)"
    fail2ban-client status "$LIVE_JAIL" >/dev/null
    fail2ban-client status "$READY_JAIL" >/dev/null
    scanner_observation_enabled && fail2ban-client status "$SCANNER_JAIL" >/dev/null
    assert_no_firewall_policy
    firewall_after="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    [[ "$firewall_before" == "$firewall_after" ]] || {
      echo 'Firewall rules changed while enabling observation.' >&2
      exit 1
    }
    installation_accepted='true'
    status_json
    ;;
  --disable-observe)
    # Arm emergency fail-open cleanup before any health or provenance check.
    # A failed acceptance check must return non-zero but still stop observation.
    installation_started='true'
    check_host
    check_log
    systemctl is-active --quiet fail2ban.service || {
      echo 'Fail2ban must be active before disabling observation.' >&2
      exit 1
    }
    assert_managed_files_match
    assert_no_unreviewed_overrides
    assert_only_approved_jails
    firewall_before="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    fail2ban-client stop "$LIVE_JAIL"
    fail2ban-client stop "$READY_JAIL"
    scanner_observation_enabled && fail2ban-client stop "$SCANNER_JAIL"
    rm -f \
      "$CONFIG_ROOT/jail.d/bookpile-observe.local" \
      "$CONFIG_ROOT/jail.d/zz-bookpile-scanner-observe.local"
    fail2ban-client -t
    assert_no_unreviewed_overrides
    assert_no_enabled_jails
    fail2ban-client reload
    wait_for_server
    assert_runtime_jail_count 0
    assert_no_firewall_policy
    firewall_after="$(nft -j --stateless list ruleset | sha256sum | cut -d' ' -f1)"
    [[ "$firewall_before" == "$firewall_after" ]] || {
      echo 'Firewall rules changed while disabling observation.' >&2
      exit 1
    }
    installation_accepted='true'
    status_json
    ;;
  --check)
    check_host
    check_log
    command -v fail2ban-client >/dev/null
    assert_optional_scanner_files_match
    fail2ban-client -t
    assert_only_approved_jails
    [[ -f /var/lib/fail2ban/fail2ban.sqlite3 ]]
    assert_no_firewall_policy
    status_json
    ;;
  --provenance-check)
    check_host
    check_log
    command -v fail2ban-client >/dev/null
    assert_managed_files_match true
    assert_no_unreviewed_overrides
    fail2ban-client -t
    printf '{"configuration_provenance":"accepted"}\n'
    ;;
esac
