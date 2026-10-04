#!/usr/bin/env bash

set -Eeuo pipefail

test_directory="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
source_script="${test_directory}/../deploy-staging.sh"
target_revision="0123456789abcdef0123456789abcdef01234567"
short_revision="0123456789ab"
temporary_root="$(mktemp -d)"
trap 'rm -rf "${temporary_root}"' EXIT

make_fixture() {
  local name="$1"
  local fixture="${temporary_root}/${name}"
  mkdir -p "${fixture}/server/deploy" "${fixture}/fake-bin"
  cp "${source_script}" "${fixture}/server/deploy/deploy-staging.sh"
  : >"${fixture}/server/compose.production.yaml"
  cat >"${fixture}/server/.env.staging" <<'EOF'
BOOKPILE_ENV_FILE=.env.staging
BOOKPILE_BACKUP_ENV_FILE=.env.staging.backup
BOOKPILE_SERVER_DEPLOYMENT_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
BOOKPILE_SERVER_PUBLIC_BASE_URL=https://staging.example.test
EOF
  cat >"${fixture}/server/.env.staging.backup" <<'EOF'
BOOKPILE_SERVER_DEPLOYMENT_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
EOF
  chmod 600 "${fixture}/server/.env.staging" "${fixture}/server/.env.staging.backup"

  cat >"${fixture}/fake-bin/git" <<EOF
#!/usr/bin/env bash
case "\$1" in
  branch) printf '%s\\n' main ;;
  status)
    if [[ " \$* " == *" --untracked-files=all "* ]]; then
      printf '%s' "\${FAKE_GIT_STATUS:-}"
    fi
    ;;
  fetch) ;;
  rev-list) printf '%s\\n' '0 0' ;;
  rev-parse)
    if [[ "\${2:-}" == --short=12 ]]; then
      printf '%s\\n' '${short_revision}'
    else
      printf '%s\\n' '${target_revision}'
    fi
    ;;
  *) printf 'unexpected git command: %s\\n' "\$*" >&2; exit 70 ;;
esac
EOF

  cat >"${fixture}/fake-bin/docker" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"${FAKE_DOCKER_LOG}"
if [[ "$*" == *"backup create"* ]]; then
  printf '%s\n' '{"backup_id":"fixture","verified":true}'
elif [[ "$*" == *"bookpile-maintenance check --deep"* ]]; then
  if [[ "${FAKE_DEEP_HEALTHY:-true}" == "true" ]]; then
    printf '%s\n' '{"healthy":true}'
  else
    printf '%s\n' '{"healthy":false}'
  fi
fi
EOF

  cat >"${fixture}/fake-bin/curl" <<EOF
#!/usr/bin/env bash
if [[ -n "\${FAKE_CURL_LOG:-}" ]]; then
  printf '%s\\n' "\$*" >>"\${FAKE_CURL_LOG}"
fi
attempt=0
if [[ -n "\${FAKE_CURL_COUNTER:-}" && -f "\${FAKE_CURL_COUNTER}" ]]; then
  attempt="\$(<"\${FAKE_CURL_COUNTER}")"
fi
attempt="\$((attempt + 1))"
if [[ -n "\${FAKE_CURL_COUNTER:-}" ]]; then
  printf '%s\\n' "\${attempt}" >"\${FAKE_CURL_COUNTER}"
fi
if [[ "\${FAKE_PUBLIC_HEALTH_MODE:-ready}" == "fail" \
  || "\${attempt}" -le "\${FAKE_CURL_FAILURES_BEFORE_SUCCESS:-0}" ]]; then
  printf '%s\\n' 'fixture connection refused' >&2
  exit 7
fi
url="\${!#}"
if [[ "\${url}" == */health/live ]]; then
  printf '%s\\n' '{"status":"alive","revision":"${target_revision}"}'
else
  printf '%s\\n' '{"status":"ready","revision":"${target_revision}"}'
fi
EOF
  cat >"${fixture}/fake-bin/flock" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  chmod +x \
    "${fixture}/fake-bin/git" \
    "${fixture}/fake-bin/docker" \
    "${fixture}/fake-bin/curl" \
    "${fixture}/fake-bin/flock"
  printf '%s\n' "${fixture}"
}

successful_fixture="$(make_fixture success)"
successful_log="${successful_fixture}/docker.log"
successful_curl_log="${successful_fixture}/curl.log"
successful_output="${successful_fixture}/deploy.out"
PATH="${successful_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${successful_log}" \
FAKE_CURL_LOG="${successful_curl_log}" \
BOOKPILE_DEPLOY_LOCK_FILE="${successful_fixture}/deploy.lock" \
  bash "${successful_fixture}/server/deploy/deploy-staging.sh" --yes >"${successful_output}"

grep -qx "BOOKPILE_SERVER_DEPLOYMENT_REVISION=${target_revision}" \
  "${successful_fixture}/server/.env.staging"
grep -qx "BOOKPILE_API_IMAGE=bookpile-api:git-${short_revision}" \
  "${successful_fixture}/server/.env.staging"
grep -qx "BOOKPILE_WEB_IMAGE=bookpile-web:git-${short_revision}" \
  "${successful_fixture}/server/.env.staging"
grep -qx "BOOKPILE_BACKUP_IMAGE=bookpile-backup:git-${short_revision}" \
  "${successful_fixture}/server/.env.staging"
grep -q "backup create" "${successful_log}"
grep -q "run --rm migrate" "${successful_log}"
grep -q "bookpile-maintenance check --deep" "${successful_log}"
grep -q '^previous_revision=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$' \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"
grep -q '^pre_deployment_backup_id=fixture$' \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"
grep -q 'Previous revision: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' "${successful_output}"
grep -q 'Pre-deployment backup: fixture' "${successful_output}"
grep -q 'Assisted application rollback' "${successful_output}"
test -f "${successful_fixture}/.bookpile-runtime/deployments/rollback-${short_revision}.env"
test -f "${successful_fixture}/.bookpile-runtime/deployments/rollback-${short_revision}.backup.env"

retry_fixture="$(make_fixture retry)"
retry_log="${retry_fixture}/docker.log"
retry_curl_log="${retry_fixture}/curl.log"
retry_counter="${retry_fixture}/curl.counter"
PATH="${retry_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${retry_log}" \
FAKE_CURL_LOG="${retry_curl_log}" \
FAKE_CURL_COUNTER="${retry_counter}" \
FAKE_CURL_FAILURES_BEFORE_SUCCESS=2 \
BOOKPILE_DEPLOY_HEALTH_RETRY_DELAY_SECONDS=0 \
BOOKPILE_DEPLOY_LOCK_FILE="${retry_fixture}/deploy.lock" \
  bash "${retry_fixture}/server/deploy/deploy-staging.sh" --yes >/dev/null 2>&1
if [[ "$(wc -l <"${retry_curl_log}")" -ne 4 ]]; then
  echo "Transient public-health failure was not retried as expected." >&2
  exit 1
fi

dirty_fixture="$(make_fixture dirty)"
dirty_log="${dirty_fixture}/docker.log"
if PATH="${dirty_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${dirty_log}" \
  FAKE_GIT_STATUS='?? server/migrations/untracked_revision.py' \
  BOOKPILE_DEPLOY_LOCK_FILE="${dirty_fixture}/deploy.lock" \
    bash "${dirty_fixture}/server/deploy/deploy-staging.sh" --check >/dev/null 2>&1; then
  echo "Expected an untracked source file to fail the deployment preflight." >&2
  exit 1
fi
if [[ -e "${dirty_log}" ]]; then
  echo "Dirty-worktree preflight reached Docker unexpectedly." >&2
  exit 1
fi

failure_fixture="$(make_fixture failure)"
failure_log="${failure_fixture}/docker.log"
if PATH="${failure_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${failure_log}" \
  FAKE_DEEP_HEALTHY=false \
  BOOKPILE_DEPLOY_LOCK_FILE="${failure_fixture}/deploy.lock" \
    bash "${failure_fixture}/server/deploy/deploy-staging.sh" --yes >/dev/null 2>&1; then
  echo "Expected an unhealthy deep check to fail the deployment." >&2
  exit 1
fi

grep -qx \
  "BOOKPILE_SERVER_DEPLOYMENT_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa" \
  "${failure_fixture}/server/.env.staging"
if grep -q '^BOOKPILE_API_IMAGE=' "${failure_fixture}/server/.env.staging"; then
  echo "Failure path did not restore the previous environment file." >&2
  exit 1
fi
if [[ "$(grep -c 'up -d --no-deps --force-recreate api email-worker web' "${failure_log}")" -ne 2 ]]; then
  echo "Failure path did not attempt the application rollback." >&2
  exit 1
fi

health_failure_fixture="$(make_fixture health-failure)"
health_failure_log="${health_failure_fixture}/docker.log"
health_failure_curl_log="${health_failure_fixture}/curl.log"
health_failure_output="${health_failure_fixture}/deploy.out"
if PATH="${health_failure_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${health_failure_log}" \
  FAKE_CURL_LOG="${health_failure_curl_log}" \
  FAKE_PUBLIC_HEALTH_MODE=fail \
  BOOKPILE_DEPLOY_HEALTH_ATTEMPTS=3 \
  BOOKPILE_DEPLOY_HEALTH_RETRY_DELAY_SECONDS=0 \
  BOOKPILE_DEPLOY_LOCK_FILE="${health_failure_fixture}/deploy.lock" \
    bash "${health_failure_fixture}/server/deploy/deploy-staging.sh" --yes \
      >"${health_failure_output}" 2>&1; then
  echo "Expected exhausted public-health retries to fail the deployment." >&2
  exit 1
fi
if [[ "$(wc -l <"${health_failure_curl_log}")" -ne 3 ]]; then
  echo "Public-health failure did not exhaust the configured attempts." >&2
  exit 1
fi
grep -q 'Public /health/live attempt 3/3 could not connect' "${health_failure_output}"
grep -q 'Public health verification failed. Current service state:' "${health_failure_output}"
grep -q 'compose .* ps' "${health_failure_log}"
grep -q 'logs --since=5m --tail=100 api email-worker web' "${health_failure_log}"
grep -qx \
  'BOOKPILE_SERVER_DEPLOYMENT_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  "${health_failure_fixture}/server/.env.staging"
if [[ "$(grep -c 'up -d --no-deps --force-recreate api email-worker web' "${health_failure_log}")" -ne 2 ]]; then
  echo "Public-health failure did not attempt the application rollback." >&2
  exit 1
fi

skip_fixture="$(make_fixture skip-backup)"
skip_log="${skip_fixture}/docker.log"
skip_output="${skip_fixture}/deploy.out"
PATH="${skip_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${skip_log}" \
FAKE_CURL_LOG="${skip_fixture}/curl.log" \
BOOKPILE_DEPLOY_LOCK_FILE="${skip_fixture}/deploy.lock" \
  bash "${skip_fixture}/server/deploy/deploy-staging.sh" --yes --skip-backup \
    >"${skip_output}" 2>&1
if grep -q 'backup create' "${skip_log}"; then
  echo "--skip-backup unexpectedly created a backup." >&2
  exit 1
fi
grep -q 'WARNING: Pre-deployment backup explicitly skipped.' "${skip_output}"
grep -q '^pre_deployment_backup_id=SKIPPED$' \
  "${skip_fixture}/.bookpile-runtime/deployments/staging-current"
grep -q 'data restoration is unavailable' "${skip_output}"

echo "Staging deployment script tests passed."
