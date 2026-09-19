#!/usr/bin/env bash

set -Eeuo pipefail
export LC_ALL=C

disk_limit="${BOOKPILE_HOST_DISK_LIMIT_PERCENT:-85}"
inode_limit="${BOOKPILE_HOST_INODE_LIMIT_PERCENT:-85}"
memory_min_mib="${BOOKPILE_HOST_MEMORY_AVAILABLE_MIN_MIB:-512}"
load_per_cpu_limit="${BOOKPILE_HOST_LOAD15_PER_CPU_LIMIT:-2}"

require_positive_integer() {
  local name="$1"
  local value="$2"
  if [[ ! "${value}" =~ ^[1-9][0-9]*$ ]]; then
    echo "${name} must be a positive integer" >&2
    exit 2
  fi
}

require_percent() {
  local name="$1"
  local value="$2"
  require_positive_integer "${name}" "${value}"
  if (( value > 100 )); then
    echo "${name} must not exceed 100" >&2
    exit 2
  fi
}

require_percent BOOKPILE_HOST_DISK_LIMIT_PERCENT "${disk_limit}"
require_percent BOOKPILE_HOST_INODE_LIMIT_PERCENT "${inode_limit}"
require_positive_integer BOOKPILE_HOST_MEMORY_AVAILABLE_MIN_MIB "${memory_min_mib}"
require_positive_integer BOOKPILE_HOST_LOAD15_PER_CPU_LIMIT "${load_per_cpu_limit}"

disk_used_percent="$(df -P / | awk 'NR == 2 { gsub(/%/, "", $5); print $5 }')"
inode_used_percent="$(df -Pi / | awk 'NR == 2 { gsub(/%/, "", $5); print $5 }')"
memory_total_mib="$(awk '/^MemTotal:/ { printf "%d", $2 / 1024 }' /proc/meminfo)"
memory_available_mib="$(awk '/^MemAvailable:/ { printf "%d", $2 / 1024 }' /proc/meminfo)"
swap_total_mib="$(awk '/^SwapTotal:/ { printf "%d", $2 / 1024 }' /proc/meminfo)"
cpu_count="$(getconf _NPROCESSORS_ONLN)"
load15="$(awk '{ print $3 }' /proc/loadavg)"
require_positive_integer detected_cpu_count "${cpu_count}"
load15_limit="$((cpu_count * load_per_cpu_limit))"

healthy=true
exit_code=0
disk_state=ready
inode_state=ready
memory_state=ready
load_state=ready

if (( disk_used_percent >= disk_limit )); then
  healthy=false
  exit_code=1
  disk_state=unavailable
fi
if (( inode_used_percent >= inode_limit )); then
  healthy=false
  exit_code=1
  inode_state=unavailable
fi
if (( memory_available_mib < memory_min_mib )); then
  healthy=false
  exit_code=1
  memory_state=unavailable
fi
if awk -v value="${load15}" -v limit="${load15_limit}" 'BEGIN { exit !(value > limit) }'; then
  healthy=false
  exit_code=1
  load_state=unavailable
fi

printf '{"checks":{"disk":"%s","inodes":"%s","load":"%s","memory":"%s"},' \
  "${disk_state}" "${inode_state}" "${load_state}" "${memory_state}"
printf '"counters":{"cpu_count":%d,"disk_used_percent":%d,"inode_used_percent":%d,' \
  "${cpu_count}" "${disk_used_percent}" "${inode_used_percent}"
printf '"load15":%s,"load15_limit":%d,"memory_available_mib":%d,"memory_total_mib":%d,' \
  "${load15}" "${load15_limit}" "${memory_available_mib}" "${memory_total_mib}"
printf '"swap_total_mib":%d},"healthy":%s}\n' "${swap_total_mib}" "${healthy}"

exit "${exit_code}"
