from pathlib import Path


ROOT = Path(__file__).parents[1]


def test_compose_separates_runtime_migrator_and_audit_credentials() -> None:
    compose = (ROOT / "compose.production.yaml").read_text(encoding="utf-8")
    assert "BOOKPILE_SERVER_MIGRATOR_DATABASE_URL" in compose
    assert "BOOKPILE_ADMIN_AUDIT_ENV_FILE" in compose
    assert "BOOKPILE_ADMIN_AUDIT_VERIFIER_ENV_FILE" in compose
    assert "BOOKPILE_ADMIN_AUDIT_RETENTION_ENV_FILE" in compose
    assert "database-role-provisioner" in compose
    assert 'profiles: ["administration"]' in compose
    assert "BOOKPILE_RUNTIME_ENV_FILE" in compose
    assert "BOOKPILE_SERVER_DEPLOYMENT_REVISION: ${BOOKPILE_SERVER_DEPLOYMENT_REVISION}" in compose
    api_anchor = compose.split("x-api-environment:", 1)[1].split(
        "x-container-logging:", 1
    )[0]
    assert "BOOKPILE_SERVER_APP_DATABASE_URL" not in api_anchor
    assert "BOOKPILE_SERVER_MIGRATOR_DATABASE_URL" not in api_anchor


def test_role_provisioner_never_prints_or_places_passwords_in_arguments() -> None:
    source = (ROOT / "deploy" / "provision-bookpile-database-roles.py").read_text(
        encoding="utf-8"
    )
    assert "passwords_exposed\": False" in source
    assert "print(password" not in source
    assert "sys.argv" not in source.split("passwords =", 1)[1]
    assert "shell=True" not in source


def test_deployment_provisions_roles_between_migration_and_restart() -> None:
    deployment = (ROOT / "deploy" / "deploy-staging.sh").read_text(encoding="utf-8")
    migration = deployment.index('run --rm migrate')
    provision = deployment.index('run --rm database-role-provisioner')
    identity_check = deployment.index(
        '--entrypoint /usr/local/bin/bookpile-database-role-check api', provision
    )
    restart = deployment.index(
        'up -d --no-deps --force-recreate api email-worker web', provision
    )
    assert migration < provision < identity_check < restart
    assert "BOOKPILE_A3_DATABASE_ROLES_ENABLED=true" in deployment
    assert "A3 runtime environment contains a deployment" in deployment
    assert "BOOKPILE_RUNTIME_ENV_FILE" in deployment
    assert "BOOKPILE_SERVER_APP_DATABASE_URL" in deployment


def test_retention_selects_only_the_contiguous_expired_prefix() -> None:
    migration = (
        ROOT / "migrations" / "versions" / "0025_immutable_admin_audit.py"
    ).read_text(encoding="utf-8")
    assert "SELECT min(recent.sequence_id)" in migration
    assert "recent.occurred_at >= v_cutoff" in migration
    assert "entry.sequence_id < COALESCE" in migration


def test_scheduled_application_jobs_use_the_sanitized_runtime_environment() -> None:
    for name in (
        "bookpile-maintenance.service.example",
        "bookpile-operations-check.service.example",
        "bookpile-deep-check.service.example",
    ):
        unit = (ROOT / "deploy" / "systemd" / name).read_text(encoding="utf-8")
        assert (
            "Environment=BOOKPILE_RUNTIME_ENV_FILE="
            "/opt/bookpile/server/.env.production.runtime"
        ) in unit
