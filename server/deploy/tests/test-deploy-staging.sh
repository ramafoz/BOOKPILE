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
  cp "${test_directory}/../rollback-staging.sh" \
    "${fixture}/server/deploy/rollback-staging.sh"
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
public_revision="\${FAKE_PUBLIC_REVISION:-${target_revision}}"
if [[ "\${url}" == */health/live ]]; then
  printf '%s\\n' "{\"status\":\"alive\",\"revision\":\"\${public_revision}\"}"
else
  printf '%s\\n' "{\"status\":\"ready\",\"revision\":\"\${public_revision}\"}"
fi
EOF
  cat >"${fixture}/fake-bin/flock" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  cat >"${fixture}/fake-bin/stat" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' 600
EOF
  cat >"${fixture}/fake-bin/cp" <<'EOF'
#!/usr/bin/env bash
source_path="${@: -2:1}"
destination_path="${@: -1}"
if [[ "${FAKE_CP_FAIL_ROLLBACK_BACKUP_ONCE:-false}" == "true" \
  && "${source_path}" == */rollback-*.backup.env \
  && "${destination_path}" == */server/.env.staging.backup \
  && ! -e "${FAKE_CP_FAILURE_MARKER}" ]]; then
  : >"${FAKE_CP_FAILURE_MARKER}"
  printf '%s\n' 'partially replaced backup environment' >"${destination_path}"
  exit 74
fi
exec /usr/bin/cp "$@"
EOF
  chmod +x \
    "${fixture}/fake-bin/git" \
    "${fixture}/fake-bin/docker" \
    "${fixture}/fake-bin/curl" \
    "${fixture}/fake-bin/flock" \
    "${fixture}/fake-bin/stat" \
    "${fixture}/fake-bin/cp"
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
grep -q "run --rm --no-deps --entrypoint /usr/local/bin/migrate-caddy-access-log-rolls web" \
  "${successful_log}"
grep -q "bookpile-maintenance check --deep" "${successful_log}"
grep -q '^previous_revision=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$' \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"
grep -q '^pre_deployment_backup_id=fixture$' \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"
grep -q 'Previous revision: aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' "${successful_output}"
grep -q 'Pre-deployment backup: fixture' "${successful_output}"
grep -q 'Confirmed application rollback' "${successful_output}"
grep -q 'bash server/deploy/rollback-staging.sh' "${successful_output}"
grep -q 'requires typing ROLLBACK' "${successful_output}"
if grep -q "cp -p .*rollback-${short_revision}" "${successful_output}"; then
  echo "Deployment output exposed an unconfirmed executable rollback recipe." >&2
  exit 1
fi
test -f "${successful_fixture}/.bookpile-runtime/deployments/rollback-${short_revision}.env"
test -f "${successful_fixture}/.bookpile-runtime/deployments/rollback-${short_revision}.backup.env"

rollback_cancel_output="${successful_fixture}/rollback-cancel.out"
if printf '%s\n' 'not-rollback' | PATH="${successful_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${successful_log}" \
  FAKE_CURL_LOG="${successful_curl_log}" \
  BOOKPILE_DEPLOY_LOCK_FILE="${successful_fixture}/deploy.lock" \
    bash "${successful_fixture}/server/deploy/rollback-staging.sh" \
      >"${rollback_cancel_output}" 2>&1; then
  echo "A rollback without the exact confirmation unexpectedly succeeded." >&2
  exit 1
fi
grep -q 'Rollback cancelled.' "${rollback_cancel_output}"
grep -qx "BOOKPILE_SERVER_DEPLOYMENT_REVISION=${target_revision}" \
  "${successful_fixture}/server/.env.staging"

rollback_output="${successful_fixture}/rollback.out"
printf '%s\n' 'ROLLBACK' | PATH="${successful_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${successful_log}" \
  FAKE_CURL_LOG="${successful_curl_log}" \
  FAKE_PUBLIC_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  BOOKPILE_DEPLOY_LOCK_FILE="${successful_fixture}/deploy.lock" \
    bash "${successful_fixture}/server/deploy/rollback-staging.sh" \
      >"${rollback_output}" 2>&1
grep -q 'Current revision:  0123456789abcdef0123456789abcdef01234567' \
  "${rollback_output}"
grep -q 'Restore revision:  aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  "${rollback_output}"
grep -q 'Staging application rollback completed successfully' "${rollback_output}"
grep -qx 'BOOKPILE_SERVER_DEPLOYMENT_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  "${successful_fixture}/server/.env.staging"
grep -qx 'revision=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa' \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"
grep -qx "previous_revision=${target_revision}" \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"
grep -Eq '^rollback_environment=.*/forward-0123456789ab-[0-9]{8}T[0-9]{6}Z.env$' \
  "${successful_fixture}/.bookpile-runtime/deployments/staging-current"

rollback_failure_fixture="$(make_fixture rollback-failure)"
rollback_failure_log="${rollback_failure_fixture}/docker.log"
PATH="${rollback_failure_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${rollback_failure_log}" \
FAKE_CURL_LOG="${rollback_failure_fixture}/curl.log" \
BOOKPILE_DEPLOY_LOCK_FILE="${rollback_failure_fixture}/deploy.lock" \
  bash "${rollback_failure_fixture}/server/deploy/deploy-staging.sh" --yes >/dev/null
if printf '%s\n' 'ROLLBACK' | PATH="${rollback_failure_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${rollback_failure_log}" \
  FAKE_PUBLIC_HEALTH_MODE=fail \
  BOOKPILE_DEPLOY_HEALTH_ATTEMPTS=1 \
  BOOKPILE_DEPLOY_HEALTH_RETRY_DELAY_SECONDS=0 \
  BOOKPILE_DEPLOY_LOCK_FILE="${rollback_failure_fixture}/deploy.lock" \
    bash "${rollback_failure_fixture}/server/deploy/rollback-staging.sh" \
      >/dev/null 2>&1; then
  echo "Expected failed rollback health to restore the forward release." >&2
  exit 1
fi
grep -qx "BOOKPILE_SERVER_DEPLOYMENT_REVISION=${target_revision}" \
  "${rollback_failure_fixture}/server/.env.staging"
if [[ "$(grep -c 'up -d --no-deps --force-recreate api email-worker web' \
  "${rollback_failure_log}")" -ne 3 ]]; then
  echo "Failed rollback did not recreate the original application state." >&2
  exit 1
fi

partial_copy_fixture="$(make_fixture partial-copy-failure)"
partial_copy_log="${partial_copy_fixture}/docker.log"
PATH="${partial_copy_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${partial_copy_log}" \
FAKE_CURL_LOG="${partial_copy_fixture}/curl.log" \
BOOKPILE_DEPLOY_LOCK_FILE="${partial_copy_fixture}/deploy.lock" \
  bash "${partial_copy_fixture}/server/deploy/deploy-staging.sh" --yes >/dev/null
if printf '%s\n' 'ROLLBACK' | PATH="${partial_copy_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${partial_copy_log}" \
  FAKE_CP_FAIL_ROLLBACK_BACKUP_ONCE=true \
  FAKE_CP_FAILURE_MARKER="${partial_copy_fixture}/cp-failed" \
  BOOKPILE_DEPLOY_LOCK_FILE="${partial_copy_fixture}/deploy.lock" \
    bash "${partial_copy_fixture}/server/deploy/rollback-staging.sh" \
      >/dev/null 2>&1; then
  echo "Expected the partial rollback copy failure to fail closed." >&2
  exit 1
fi
grep -qx "BOOKPILE_SERVER_DEPLOYMENT_REVISION=${target_revision}" \
  "${partial_copy_fixture}/server/.env.staging"
grep -qx "BOOKPILE_SERVER_DEPLOYMENT_REVISION=${target_revision}" \
  "${partial_copy_fixture}/server/.env.staging.backup"
grep -qx "revision=${target_revision}" \
  "${partial_copy_fixture}/.bookpile-runtime/deployments/staging-current"
if [[ "$(grep -c 'up -d --no-deps --force-recreate api email-worker web' \
  "${partial_copy_log}")" -ne 2 ]]; then
  echo "Partial environment copy failure did not restore the forward application." >&2
  exit 1
fi

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

leading_zero_fixture="$(make_fixture leading-zero-attempts)"
leading_zero_log="${leading_zero_fixture}/docker.log"
leading_zero_output="${leading_zero_fixture}/deploy.out"
if PATH="${leading_zero_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${leading_zero_log}" \
  BOOKPILE_DEPLOY_HEALTH_ATTEMPTS=08 \
  BOOKPILE_DEPLOY_LOCK_FILE="${leading_zero_fixture}/deploy.lock" \
    bash "${leading_zero_fixture}/server/deploy/deploy-staging.sh" --check \
      >"${leading_zero_output}" 2>&1; then
  echo "Expected a leading-zero health-attempt count to fail validation." >&2
  exit 1
fi
grep -q 'BOOKPILE_DEPLOY_HEALTH_ATTEMPTS must be a positive integer.' \
  "${leading_zero_output}"
if [[ -e "${leading_zero_log}" ]]; then
  echo "Invalid health-attempt validation reached Docker unexpectedly." >&2
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

a3_fixture="$(make_fixture a3-separated-runtime)"
a3_log="${a3_fixture}/docker.log"
cat >>"${a3_fixture}/server/.env.staging" <<'EOF'
BOOKPILE_A3_DATABASE_ROLES_ENABLED=true
BOOKPILE_A3_RUNTIME_ENV_FILE=.env.staging.runtime
BOOKPILE_SERVER_APP_DATABASE_URL=postgresql+psycopg://bookpile_app:fixture-app@db:5432/bookpile
BOOKPILE_SERVER_MIGRATOR_DATABASE_URL=postgresql+psycopg://bookpile:fixture-migrator@db:5432/bookpile
EOF
cat >"${a3_fixture}/server/.env.staging.runtime" <<'EOF'
BOOKPILE_SERVER_DATABASE_URL=postgresql+psycopg://bookpile_app:fixture-app@db:5432/bookpile
BOOKPILE_SERVER_PUBLIC_BASE_URL=https://staging.example.test
EOF
chmod 600 "${a3_fixture}/server/.env.staging.runtime"
PATH="${a3_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${a3_log}" \
FAKE_CURL_LOG="${a3_fixture}/curl.log" \
BOOKPILE_DEPLOY_LOCK_FILE="${a3_fixture}/deploy.lock" \
  bash "${a3_fixture}/server/deploy/deploy-staging.sh" --yes >/dev/null
grep -q 'run --rm database-role-provisioner' "${a3_log}"
grep -q -- '--entrypoint /usr/local/bin/bookpile-database-role-check api' "${a3_log}"
printf '%s\n' 'ROLLBACK' | PATH="${a3_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${a3_log}" \
  FAKE_CURL_LOG="${a3_fixture}/curl.log" \
  FAKE_PUBLIC_REVISION=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa \
  BOOKPILE_DEPLOY_LOCK_FILE="${a3_fixture}/deploy.lock" \
    bash "${a3_fixture}/server/deploy/rollback-staging.sh" >/dev/null
if [[ "$(grep -c -- '--entrypoint /usr/local/bin/bookpile-database-role-check api' \
  "${a3_log}")" -ne 2 ]]; then
  echo "Confirmed A3 rollback did not verify the restored application identity." >&2
  exit 1
fi

unsafe_a3_fixture="$(make_fixture a3-unsafe-runtime)"
unsafe_a3_log="${unsafe_a3_fixture}/docker.log"
cat >>"${unsafe_a3_fixture}/server/.env.staging" <<'EOF'
BOOKPILE_A3_DATABASE_ROLES_ENABLED=true
BOOKPILE_A3_RUNTIME_ENV_FILE=.env.staging.runtime
BOOKPILE_SERVER_APP_DATABASE_URL=postgresql+psycopg://bookpile_app:fixture-app@db:5432/bookpile
BOOKPILE_SERVER_MIGRATOR_DATABASE_URL=postgresql+psycopg://bookpile:fixture-migrator@db:5432/bookpile
EOF
cat >"${unsafe_a3_fixture}/server/.env.staging.runtime" <<'EOF'
BOOKPILE_SERVER_DATABASE_URL=postgresql+psycopg://bookpile_app:fixture-app@db:5432/bookpile
BOOKPILE_SERVER_MIGRATOR_DATABASE_URL=postgresql+psycopg://bookpile:leaked@db:5432/bookpile
EOF
chmod 600 "${unsafe_a3_fixture}/server/.env.staging.runtime"
if PATH="${unsafe_a3_fixture}/fake-bin:${PATH}" \
  FAKE_DOCKER_LOG="${unsafe_a3_log}" \
  BOOKPILE_DEPLOY_LOCK_FILE="${unsafe_a3_fixture}/deploy.lock" \
    bash "${unsafe_a3_fixture}/server/deploy/deploy-staging.sh" --check \
      >/dev/null 2>&1; then
  echo "Expected a privileged secret in the A3 runtime env to fail preflight." >&2
  exit 1
fi
if [[ -e "${unsafe_a3_log}" ]]; then
  echo "Unsafe A3 runtime env reached Docker unexpectedly." >&2
  exit 1
fi

echo "Staging deployment script tests passed."
