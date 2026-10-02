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
  status) ;;
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
printf '%s\\n' '{"status":"ready","revision":"${target_revision}"}'
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
PATH="${successful_fixture}/fake-bin:${PATH}" \
FAKE_DOCKER_LOG="${successful_log}" \
BOOKPILE_DEPLOY_LOCK_FILE="${successful_fixture}/deploy.lock" \
  bash "${successful_fixture}/server/deploy/deploy-staging.sh" --yes >/dev/null

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

echo "Staging deployment script tests passed."
