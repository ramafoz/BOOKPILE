#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
  cat <<'EOF'
Usage: bash server/deploy/deploy-staging.sh [--check] [--yes]

Deploy the latest fast-forwardable origin/main revision to BOOKPILE staging.

  --check  Validate the host, repository and Compose configuration only.
  --yes    Do not ask for interactive confirmation.
  --help   Show this help.

The script must run from a clean main branch on the staging host. It creates a
verified off-site backup, builds commit-addressed images, runs migrations,
recreates the application services and verifies public and deep health.
EOF
}

original_arguments=("$@")
check_only=false
assume_yes=false

while [[ "$#" -gt 0 ]]; do
  case "$1" in
    --check)
      check_only=true
      ;;
    --yes)
      assume_yes=true
      ;;
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
  shift
done

script_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repository_root="$(cd -- "${script_directory}/../.." && pwd)"
environment_file="${BOOKPILE_DEPLOY_ENV_FILE:-${repository_root}/server/.env.staging}"
backup_environment_file="${BOOKPILE_DEPLOY_BACKUP_ENV_FILE:-${repository_root}/server/.env.staging.backup}"
compose_file="${repository_root}/server/compose.production.yaml"
lock_file="${BOOKPILE_DEPLOY_LOCK_FILE:-/tmp/bookpile-staging-deploy.lock}"

cd "${repository_root}"

for command_name in awk curl docker flock git grep mktemp sed; do
  if ! command -v "${command_name}" >/dev/null 2>&1; then
    echo "Required command is unavailable: ${command_name}" >&2
    exit 1
  fi
done

exec 9>"${lock_file}"
if ! flock -n 9; then
  echo "Another staging deployment is already running (${lock_file})." >&2
  exit 1
fi

if [[ ! -r "${environment_file}" || ! -w "${environment_file}" ]]; then
  echo "Staging environment file must be readable and writable: ${environment_file}" >&2
  exit 1
fi
if [[ ! -r "${backup_environment_file}" || ! -w "${backup_environment_file}" ]]; then
  echo "Backup environment file must be readable and writable: ${backup_environment_file}" >&2
  exit 1
fi

current_branch="$(git branch --show-current)"
if [[ "${current_branch}" != "main" ]]; then
  echo "Refusing to deploy branch '${current_branch}'. Switch to main first." >&2
  exit 1
fi
if [[ -n "$(git status --porcelain --untracked-files=no)" ]]; then
  echo "Refusing to deploy a repository with tracked changes." >&2
  git status --short >&2
  exit 1
fi

echo "Fetching origin/main..."
git fetch --quiet origin main
read -r local_only remote_only < <(git rev-list --left-right --count main...origin/main)
if [[ "${local_only}" -ne 0 ]]; then
  echo "Local main contains commits absent from origin/main; refusing to deploy." >&2
  exit 1
fi
if [[ "${remote_only}" -ne 0 ]]; then
  echo "Fast-forwarding main by ${remote_only} commit(s)..."
  git merge --ff-only --quiet origin/main
  if [[ "${BOOKPILE_DEPLOY_REEXECUTED:-false}" != "true" ]]; then
    exec env BOOKPILE_DEPLOY_REEXECUTED=true \
      bash "${repository_root}/server/deploy/deploy-staging.sh" "${original_arguments[@]}"
  fi
fi

target_revision="$(git rev-parse HEAD)"
short_revision="$(git rev-parse --short=12 HEAD)"
api_image="bookpile-api:git-${short_revision}"
web_image="bookpile-web:git-${short_revision}"
backup_image="bookpile-backup:git-${short_revision}"
compose=(docker compose --env-file "${environment_file}" -f "${compose_file}")

read_env_value() {
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

public_base_url="$(read_env_value "${environment_file}" BOOKPILE_SERVER_PUBLIC_BASE_URL)"
previous_revision="$(read_env_value "${environment_file}" BOOKPILE_SERVER_DEPLOYMENT_REVISION)"
if [[ -z "${public_base_url}" || "${public_base_url}" != https://* ]]; then
  echo "BOOKPILE_SERVER_PUBLIC_BASE_URL must be an HTTPS URL." >&2
  exit 1
fi

echo "Validating Compose configuration..."
"${compose[@]}" --profile operations config --quiet

echo "Current revision: ${previous_revision:-unknown}"
echo "Target revision:  ${target_revision}"
echo "Public origin:    ${public_base_url}"

if [[ "${check_only}" == "true" ]]; then
  echo "Staging deployment preflight passed. No deployment changes were made."
  exit 0
fi
if [[ "${previous_revision}" == "${target_revision}" ]]; then
  echo "Staging already declares revision ${target_revision}; nothing to deploy."
  exit 0
fi

if [[ "${assume_yes}" != "true" ]]; then
  if [[ ! -t 0 ]]; then
    echo "Interactive confirmation is unavailable; rerun with --yes." >&2
    exit 1
  fi
  read -r -p "Deploy this revision to staging? Type DEPLOY: " confirmation
  if [[ "${confirmation}" != "DEPLOY" ]]; then
    echo "Deployment cancelled."
    exit 1
  fi
fi

runtime_directory="${repository_root}/.bookpile-runtime/deployments"
mkdir -p "${runtime_directory}"
backup_log="$(mktemp "${runtime_directory}/backup.XXXXXX")"
check_log="$(mktemp "${runtime_directory}/check.XXXXXX")"
saved_environment="$(mktemp "${runtime_directory}/environment.XXXXXX")"
saved_backup_environment="$(mktemp "${runtime_directory}/backup-environment.XXXXXX")"
chmod 600 "${backup_log}" "${check_log}" "${saved_environment}" "${saved_backup_environment}"
cp -p "${environment_file}" "${saved_environment}"
cp -p "${backup_environment_file}" "${saved_backup_environment}"

configuration_changed=false
deployment_succeeded=false

restore_previous_application() {
  echo "Restoring the previous application configuration..." >&2
  cp -p "${saved_environment}" "${environment_file}"
  cp -p "${saved_backup_environment}" "${backup_environment_file}"
  "${compose[@]}" up -d --no-deps --force-recreate api email-worker web >&2 || true
  echo "Database migrations were not downgraded. Inspect service health and logs." >&2
}

cleanup() {
  local status="$?"
  trap - EXIT
  if [[ "${status}" -ne 0 ]]; then
    echo "Deployment failed with status ${status}." >&2
    if [[ "${configuration_changed}" == "true" && "${deployment_succeeded}" != "true" ]]; then
      restore_previous_application
    fi
  fi
  rm -f "${backup_log}" "${check_log}" "${saved_environment}" "${saved_backup_environment}"
  exit "${status}"
}
trap cleanup EXIT

echo "Creating and verifying the pre-deployment backup..."
"${compose[@]}" --profile operations run --rm backup create 2>&1 | tee "${backup_log}"
if ! grep -Eq '"verified"[[:space:]]*:[[:space:]]*true' "${backup_log}"; then
  echo "Backup command did not report a verified snapshot; refusing to continue." >&2
  exit 1
fi

echo "Building immutable images for ${short_revision}..."
BOOKPILE_API_IMAGE="${api_image}" \
BOOKPILE_WEB_IMAGE="${web_image}" \
BOOKPILE_BACKUP_IMAGE="${backup_image}" \
  "${compose[@]}" --profile operations build api web backup
docker image inspect "${api_image}" "${web_image}" "${backup_image}" >/dev/null

set_env_value() {
  local file="$1"
  local key="$2"
  local value="$3"
  local temporary
  temporary="$(mktemp "${file}.deploy-XXXXXX")"
  chmod --reference="${file}" "${temporary}"
  awk -v key="${key}" -v value="${value}" '
    BEGIN { replaced = 0 }
    index($0, key "=") == 1 {
      if (!replaced) {
        print key "=" value
        replaced = 1
      }
      next
    }
    { print }
    END {
      if (!replaced) print key "=" value
    }
  ' "${file}" >"${temporary}"
  mv -f "${temporary}" "${file}"
}

set_env_value "${environment_file}" BOOKPILE_SERVER_DEPLOYMENT_REVISION "${target_revision}"
set_env_value "${environment_file}" BOOKPILE_API_IMAGE "${api_image}"
set_env_value "${environment_file}" BOOKPILE_WEB_IMAGE "${web_image}"
set_env_value "${environment_file}" BOOKPILE_BACKUP_IMAGE "${backup_image}"
set_env_value "${backup_environment_file}" BOOKPILE_SERVER_DEPLOYMENT_REVISION "${target_revision}"
configuration_changed=true

echo "Validating the release configuration..."
"${compose[@]}" --profile operations config --quiet

echo "Running explicit database migrations..."
"${compose[@]}" run --rm migrate

echo "Recreating application services..."
"${compose[@]}" up -d --no-deps --force-recreate api email-worker web

echo "Verifying public liveness and readiness..."
live_response="$(curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 \
  "${public_base_url}/health/live")"
ready_response="$(curl --fail --silent --show-error --retry 12 --retry-all-errors --retry-delay 5 \
  "${public_base_url}/health/ready")"
if [[ "${live_response}" != *"\"revision\":\"${target_revision}\""* ]]; then
  echo "Liveness returned a different deployment revision: ${live_response}" >&2
  exit 1
fi
if [[ "${ready_response}" != *"\"revision\":\"${target_revision}\""* ]]; then
  echo "Readiness returned a different deployment revision: ${ready_response}" >&2
  exit 1
fi

echo "Running the deep operational check..."
"${compose[@]}" --profile operations run --rm maintenance \
  bookpile-maintenance check --deep 2>&1 | tee "${check_log}"
if ! grep -Eq '"healthy"[[:space:]]*:[[:space:]]*true' "${check_log}"; then
  echo "Deep operational check did not report healthy=true." >&2
  exit 1
fi

deployment_succeeded=true
printf '%s\n' \
  "revision=${target_revision}" \
  "deployed_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  "api_image=${api_image}" \
  "web_image=${web_image}" \
  "backup_image=${backup_image}" \
  >"${runtime_directory}/staging-current"

echo "Staging deployment completed successfully at ${target_revision}."

