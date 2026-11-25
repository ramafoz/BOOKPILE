#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: bash server/deploy/rollback-staging.sh

Restore the application environment saved by the latest successful BOOKPILE
staging deployment. This recreates API, email-worker and web with the previous
images, then verifies public and deep health. It does not downgrade database
migrations or restore application data.

The command is intentionally interactive and requires typing ROLLBACK exactly.
EOF
}

if [[ "$#" -gt 0 ]]; then
  case "$1" in
    --help|-h)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage >&2
      exit 2
      ;;
  esac
fi

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_directory}/../.." && pwd)"
environment_file="${BOOKPILE_DEPLOY_ENV_FILE:-${repository_root}/server/.env.staging}"
backup_environment_file="${BOOKPILE_DEPLOY_BACKUP_ENV_FILE:-${repository_root}/server/.env.staging.backup}"
compose_file="${repository_root}/server/compose.production.yaml"
runtime_directory="${repository_root}/.bookpile-runtime/deployments"
current_marker="${runtime_directory}/staging-current"
lock_file="${BOOKPILE_DEPLOY_LOCK_FILE:-/tmp/bookpile-staging-deploy.lock}"
health_attempts="${BOOKPILE_DEPLOY_HEALTH_ATTEMPTS:-18}"
health_retry_delay_seconds="${BOOKPILE_DEPLOY_HEALTH_RETRY_DELAY_SECONDS:-5}"
health_request_timeout_seconds="${BOOKPILE_DEPLOY_HEALTH_REQUEST_TIMEOUT_SECONDS:-10}"

cd "${repository_root}"

for command_name in awk chmod cp curl date docker flock git grep mktemp readlink rm sleep stat tee; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}" >&2
    exit 1
  fi
done

exec 9>"${lock_file}"
if ! flock -n 9; then
  echo "Another staging deployment or rollback is already running (${lock_file})." >&2
  exit 1
fi

if [[ "$(git branch --show-current)" != "main" ]]; then
  echo "Refusing to roll back outside the main branch." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain=v1 --untracked-files=all)" ]]; then
  echo "Refusing to roll back from a dirty repository." >&2
  git status --short --untracked-files=all >&2
  exit 1
fi
if [[ ! -r "${current_marker}" || -L "${current_marker}" ]]; then
  echo "The latest staging deployment marker is unavailable: ${current_marker}" >&2
  exit 1
fi
if [[ ! -r "${environment_file}" || ! -w "${environment_file}" \
  || ! -r "${backup_environment_file}" || ! -w "${backup_environment_file}" ]]; then
  echo "The staging environment files must be readable and writable." >&2
  exit 1
fi
if ! [[ "${health_attempts}" =~ ^[1-9][0-9]*$ \
  && "${health_retry_delay_seconds}" =~ ^[0-9]+$ \
  && "${health_request_timeout_seconds}" =~ ^[1-9][0-9]*$ ]]; then
  echo "Rollback health retry settings are invalid." >&2
  exit 1
fi

read_key() {
  local file="$1"
  local key="$2"
  awk -v key="${key}" '
    index($0, key "=") == 1 {
      value = substr($0, length(key) + 2)
      sub(/\r$/, "", value)
      print value
      exit
    }
  ' "${file}"
}

resolve_server_path() {
  local value="$1"
  if [[ "${value}" = /* ]]; then
    printf '%s\n' "${value}"
  else
    printf '%s\n' "${repository_root}/server/${value}"
  fi
}

validate_snapshot() {
  local snapshot="$1"
  local resolved runtime_resolved
  if [[ ! -f "${snapshot}" || -L "${snapshot}" || ! -r "${snapshot}" \
    || "$(stat -c '%a' "${snapshot}")" != "600" ]]; then
    echo "Rollback snapshot must be a readable regular file with mode 0600: ${snapshot}" >&2
    exit 1
  fi
  resolved="$(readlink -f -- "${snapshot}")"
  runtime_resolved="$(readlink -f -- "${runtime_directory}")"
  case "${resolved}" in
    "${runtime_resolved}"/rollback-*.env|"${runtime_resolved}"/forward-*.env) ;;
    *)
      echo "Rollback snapshot is outside the reviewed deployment directory: ${snapshot}" >&2
      exit 1
      ;;
  esac
}

configure_runtime_environment() {
  local deployment_environment="$1"
  local enabled reference app_url migrator_url runtime_url
  unset BOOKPILE_RUNTIME_ENV_FILE
  enabled="$(read_key "${deployment_environment}" BOOKPILE_A3_DATABASE_ROLES_ENABLED)"
  if [[ "${enabled}" == "true" ]]; then
    reference="$(read_key "${deployment_environment}" BOOKPILE_A3_RUNTIME_ENV_FILE)"
    app_url="$(read_key "${deployment_environment}" BOOKPILE_SERVER_APP_DATABASE_URL)"
    migrator_url="$(read_key "${deployment_environment}" BOOKPILE_SERVER_MIGRATOR_DATABASE_URL)"
    if [[ -z "${reference}" || -z "${app_url}" || -z "${migrator_url}" \
      || "${app_url}" == "${migrator_url}" ]]; then
      echo "Rollback snapshot has an invalid A3 database-role boundary." >&2
      return 1
    fi
    BOOKPILE_RUNTIME_ENV_FILE="$(resolve_server_path "${reference}")"
    export BOOKPILE_RUNTIME_ENV_FILE
    if [[ ! -f "${BOOKPILE_RUNTIME_ENV_FILE}" \
      || -L "${BOOKPILE_RUNTIME_ENV_FILE}" \
      || "$(stat -c '%a' "${BOOKPILE_RUNTIME_ENV_FILE}")" != "600" ]]; then
      echo "A3 runtime environment must be a regular file with mode 0600." >&2
      return 1
    fi
    runtime_url="$(read_key "${BOOKPILE_RUNTIME_ENV_FILE}" BOOKPILE_SERVER_DATABASE_URL)"
    if [[ "${runtime_url}" != "${app_url}" ]]; then
      echo "A3 runtime environment does not match the rollback app database URL." >&2
      return 1
    fi
  elif [[ -n "${enabled}" && "${enabled}" != "false" ]]; then
    echo "BOOKPILE_A3_DATABASE_ROLES_ENABLED must be exactly true or false." >&2
    return 1
  fi
}

deployed_revision="$(read_key "${current_marker}" revision)"
previous_revision="$(read_key "${current_marker}" previous_revision)"
rollback_environment="$(read_key "${current_marker}" rollback_environment)"
rollback_backup_environment="$(read_key "${current_marker}" rollback_backup_environment)"
pre_deployment_backup_id="$(read_key "${current_marker}" pre_deployment_backup_id)"
declared_revision="$(read_key "${environment_file}" BOOKPILE_SERVER_DEPLOYMENT_REVISION)"

for revision in "${deployed_revision}" "${previous_revision}"; do
  if ! [[ "${revision}" =~ ^[0-9a-f]{40}$ ]]; then
    echo "The staging marker does not contain two full lowercase revisions." >&2
    exit 1
  fi
done
if [[ "${declared_revision}" != "${deployed_revision}" ]]; then
  echo "Current environment revision does not match the staging marker; refusing rollback." >&2
  exit 1
fi
validate_snapshot "${rollback_environment}"
validate_snapshot "${rollback_backup_environment}"

rollback_declared_revision="$(read_key "${rollback_environment}" BOOKPILE_SERVER_DEPLOYMENT_REVISION)"
if [[ "${rollback_declared_revision}" != "${previous_revision}" ]]; then
  echo "Rollback snapshot revision does not match the staging marker." >&2
  exit 1
fi
public_base_url="$(read_key "${rollback_environment}" BOOKPILE_SERVER_PUBLIC_BASE_URL)"
if [[ -z "${public_base_url}" || "${public_base_url}" != https://* ]]; then
  echo "Rollback snapshot does not contain a valid HTTPS public origin." >&2
  exit 1
fi

printf '%s\n' \
  "Staging application rollback requested." \
  "  Current revision:  ${deployed_revision}" \
  "  Restore revision:  ${previous_revision}" \
  "  Database migrations will not be downgraded." \
  "  Backup ${pre_deployment_backup_id:-unknown} will not be restored automatically."
if ! read -r -p "Type ROLLBACK to continue: " confirmation; then
  echo "Rollback confirmation was not provided." >&2
  exit 1
fi
if [[ "${confirmation}" != "ROLLBACK" ]]; then
  echo "Rollback cancelled."
  exit 1
fi

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
forward_environment="${runtime_directory}/forward-${deployed_revision:0:12}-${timestamp}.env"
forward_backup_environment="${runtime_directory}/forward-${deployed_revision:0:12}-${timestamp}.backup.env"
health_error_log="$(mktemp "${runtime_directory}/rollback-health-error.XXXXXX")"
check_log="$(mktemp "${runtime_directory}/rollback-check.XXXXXX")"
cp -p "${environment_file}" "${forward_environment}"
cp -p "${backup_environment_file}" "${forward_backup_environment}"
chmod 600 "${forward_environment}" "${forward_backup_environment}" \
  "${health_error_log}" "${check_log}"

mutation_started=false
rollback_succeeded=false

restore_forward_application() {
  echo "Rollback failed; restoring the pre-rollback application configuration..." >&2
  cp -p "${forward_environment}" "${environment_file}"
  cp -p "${forward_backup_environment}" "${backup_environment_file}"
  if configure_runtime_environment "${environment_file}"; then
    local recovery_compose=(docker compose --env-file "${environment_file}" -f "${compose_file}")
    "${recovery_compose[@]}" --profile operations config --quiet >&2 || true
    "${recovery_compose[@]}" up -d --no-deps --force-recreate \
      api email-worker web >&2 || true
  fi
  echo "Inspect public health and service logs before taking another action." >&2
}

cleanup() {
  local status="$?"
  trap - EXIT
  if [[ "${status}" -ne 0 && "${mutation_started}" == "true" \
    && "${rollback_succeeded}" != "true" ]]; then
    restore_forward_application
  fi
  rm -f "${health_error_log}" "${check_log}"
  exit "${status}"
}
trap cleanup EXIT

mutation_started=true
cp -p "${rollback_environment}" "${environment_file}"
cp -p "${rollback_backup_environment}" "${backup_environment_file}"
configure_runtime_environment "${environment_file}"
compose=(docker compose --env-file "${environment_file}" -f "${compose_file}")

echo "Validating the rollback configuration..."
"${compose[@]}" --profile operations config --quiet
echo "Recreating the previous application services..."
"${compose[@]}" up -d --no-deps --force-recreate api email-worker web
if grep -qx 'BOOKPILE_A3_DATABASE_ROLES_ENABLED=true' "${environment_file}"; then
  echo "Verifying the restored A3 application identity..."
  "${compose[@]}" run --rm --no-deps \
    --entrypoint /usr/local/bin/bookpile-database-role-check api
fi

wait_for_public_health() {
  local endpoint="$1"
  local expected_status="$2"
  local attempt response
  for ((attempt = 1; attempt <= health_attempts; attempt += 1)); do
    : >"${health_error_log}"
    if response="$(curl --fail --silent --show-error \
      --connect-timeout "${health_request_timeout_seconds}" \
      --max-time "${health_request_timeout_seconds}" \
      "${public_base_url}${endpoint}" 2>"${health_error_log}")"; then
      if [[ "${response}" == *"\"status\":\"${expected_status}\""* \
        && "${response}" == *"\"revision\":\"${previous_revision}\""* ]]; then
        printf '%s\n' "${response}"
        return 0
      fi
      printf 'Public %s attempt %d/%d returned an unexpected payload: %s\n' \
        "${endpoint}" "${attempt}" "${health_attempts}" "${response}" >&2
    else
      printf 'Public %s attempt %d/%d could not connect: %s\n' \
        "${endpoint}" "${attempt}" "${health_attempts}" \
        "$(<"${health_error_log}")" >&2
    fi
    if [[ "${attempt}" -lt "${health_attempts}" ]]; then
      sleep "${health_retry_delay_seconds}"
    fi
  done
  return 1
}

echo "Verifying the restored application..."
live_response="$(wait_for_public_health /health/live alive)"
ready_response="$(wait_for_public_health /health/ready ready)"
echo "Public liveness confirmed: ${live_response}"
echo "Public readiness confirmed: ${ready_response}"

echo "Running the deep operational check..."
"${compose[@]}" --profile operations run --rm maintenance \
  bookpile-maintenance check --deep 2>&1 | tee "${check_log}"
if ! grep -Eq '"healthy"[[:space:]]*:[[:space:]]*true' "${check_log}"; then
  echo "Deep operational check did not report healthy=true." >&2
  exit 1
fi

printf '%s\n' \
  "revision=${previous_revision}" \
  "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "api_image=$(read_key "${environment_file}" BOOKPILE_API_IMAGE)" \
  "web_image=$(read_key "${environment_file}" BOOKPILE_WEB_IMAGE)" \
  "backup_image=$(read_key "${environment_file}" BOOKPILE_BACKUP_IMAGE)" \
  "previous_revision=${deployed_revision}" \
  "pre_deployment_backup_id=${pre_deployment_backup_id:-unknown}" \
  "rollback_environment=${forward_environment}" \
  "rollback_backup_environment=${forward_backup_environment}" \
  "rollback_completed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  >"${current_marker}"
rollback_succeeded=true

echo "Staging application rollback completed successfully at ${previous_revision}."
echo "Database migrations and application data were not rolled back."
