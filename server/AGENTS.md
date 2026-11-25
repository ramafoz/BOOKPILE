# BOOKPILE Server guidance

These rules apply to `server/` and supplement the repository root guidance.

## Data and authorization

- This is the hosted multi-user PostgreSQL edition. Every library resource must
  remain tenant-scoped; knowing a UUID is never authorization.
- Preserve Owner/Viewer boundaries, Viewer map scope, self-only personal data,
  stale-session behaviour, CSRF protection and redacted audit contracts.
- Application runtime roles must remain non-superuser and unable to read the
  immutable `admin_audit` schema. Changes to A3 or D3-L require their dedicated
  role, privacy, verifier, retention and backup tests.
- Private objects must remain authenticated, library-scoped, reconciled and
  recoverable. Never log object keys or provider credentials.

## Database changes

- Manage schema exclusively through Alembic. Never edit an existing migration
  that may have run outside disposable development databases.
- Prefer additive, backward-compatible migrations. Document downgrade limits
  and deployment ordering when a migration cannot be safely reversed.
- PostgreSQL integration tests may only target an explicitly disposable
  database whose name ends in `_test`.
- Exercise migration, constraint, tenant-isolation and concurrency behaviour
  proportionally to the change.

## Operations and deployment

- `docs/server/SERVER_OPERATIONS_AND_SECURITY.md` is the live operational
  runbook. Follow its staged enable/disable, backup, recovery and evidence
  procedures exactly.
- Never edit staging or production environment files, systemd units, Fail2ban,
  nftables or host secrets as an incidental implementation step.
- A deploy requires explicit authorization, a clean `main`, preflight, verified
  backup and revision-linked health checks. A rollback requires the dedicated
  script and exact `ROLLBACK` confirmation; it does not downgrade migrations or
  restore data.
- Preserve fail-open emergency disable paths and independent D6 controls.
  Security output remains aggregate unless the audited D3-L workflow is
  explicitly invoked.

## Validation

- Fast suite: `python -m pytest server/tests`
- Migration rehearsal: `python -m pytest server/tests/test_postgresql_integration.py`
  with the documented disposable PostgreSQL test URLs.
- Deployment/rollback changes: syntax checks plus
  `bash server/deploy/tests/test-deploy-staging.sh`.
- Defensive changes: run the affected D5/D6/D7 tests and validators, and retain
  only privacy-safe evidence.
- Changes affecting API contracts or the shared UI also require the Server
  frontend tests and build.
