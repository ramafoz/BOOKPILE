# BOOKPILE Server foundation

This directory is the isolated beginning of the hosted multi-user edition.
It does not read or modify BOOKPILE Local data.

The repository currently uses two Git worktrees. Run every command in this
document from `C:\Users\Russula\.code\_BOOKPILE_SERVER`. The sibling
`_PERSONAL_LIBRARY_MANAGER` directory is the live Local v1 installation and
must not be used for Server migrations or test databases.

## Current Server slice

- Environment-based Server configuration.
- SQLAlchemy session boundaries.
- PostgreSQL schema managed by Alembic.
- Minimal `libraries` and `books` tables.
- Read-only catalogue endpoint scoped by library ID.
- Repository and API tests proving that one library cannot read another
  library's catalogue through this slice.
- Reversible Phase 2A identity foundation: users, hashed opaque-session
  records, and structured security events.
- Phase 2B Argon2id password verification plus login/logout with opaque
  `HttpOnly` session cookies and audit events.
- Phase 2C protected-request authentication, inactivity and absolute expiry,
  CSRF enforcement, credential rotation, and global session revocation.
- Phase 2D-A temporary account invitations, stored only as token hashes and
  managed separately from future library-sharing invitations.
- Phase 2D-B atomic invitation-only registration into a
  `pending_verification` account. Registration never creates a login session.
- Phase 2E email verification/resend and password recovery with expiring,
  purpose-restricted hashed tokens. Password changes revoke every session.
- Phase 2F shared PostgreSQL-backed limits on every public identity flow,
  atomic under concurrent workers and keyed only by HMAC digests. Auth
  responses also carry baseline defensive and no-cache headers.

The authentication core now supports temporary invitation registration,
verification, password recovery, shared rate limits, and the dedicated backend
security gate. The authentication frontend is the remaining Phase 2 increment.
The Server branch is still not deployable: a path library ID is a temporary
Phase 1 input used to prove architectural scoping; it is not authorization.

## Development setup

Create an isolated environment from the repository root:

```powershell
py -3.13 -m venv server\.venv
server\.venv\Scripts\python -m pip install -e "server[dev]"
```

Run the fast isolated tests:

```powershell
server\.venv\Scripts\python -m pytest server\tests
```

The PostgreSQL integration test is skipped unless an explicitly disposable
database is configured. Its database name must end in `_test`:

```powershell
$env:BOOKPILE_SERVER_TEST_DATABASE_URL = "postgresql+psycopg://bookpile:bookpile-dev@127.0.0.1:5432/bookpile_test"
server\.venv\Scripts\python -m pytest server\tests\test_postgresql_integration.py
```

Run PostgreSQL with Docker, when Docker is available:

```powershell
docker compose -f server\compose.yaml up -d db mailpit
$env:BOOKPILE_SERVER_DATABASE_URL = "postgresql+psycopg://bookpile:bookpile-dev@127.0.0.1:5432/bookpile"
server\.venv\Scripts\alembic -c server\alembic.ini upgrade head
server\.venv\Scripts\uvicorn bookpile_server.main:app --app-dir server\src --reload --port 8100
```

The first volume initialization creates two databases:

- `bookpile` stores disposable development data.
- `bookpile_test` is emptied by migration/integration tests.

Apply migrations and optionally insert the deliberately small synthetic demo:

```powershell
server\.venv\Scripts\alembic -c server\alembic.ini upgrade head
server\.venv\Scripts\python server\scripts\seed_development.py
```

Generate or revoke a temporary beta account invitation after applying the
latest migration:

```powershell
server\.venv\Scripts\python server\scripts\manage_account_invitations.py create
server\.venv\Scripts\python server\scripts\manage_account_invitations.py revoke <invitation-uuid>
```

The registration URL is displayed once. PostgreSQL stores only its token hash.
These account invitations do not grant access to any library; library
invitations depend on the later membership model.

The seed script refuses non-development environments, remote hosts, databases
not named exactly `bookpile`, and non-PostgreSQL targets. Its records are not
copied from a Local catalogue.

Do not reuse production credentials or Local catalogue paths in development.

## Safety status

The migration and isolation gate now upgrades through Phase 2F against
PostgreSQL 17, checks catalogue isolation, identity/session/invitation/action
records, concurrent invitation consumption, atomic concurrent rate limiting,
and each incremental rollback. It then downgrades disposable `bookpile_test`
until no BOOKPILE application tables remain. Alembic may retain its empty
administrative `alembic_version` table.

The committed password is for loopback-only local development. Hosted and
staging environments must obtain unique secrets from deployment configuration.
Production refuses to start with the development rate-limit HMAC secret,
insecure session cookies, or a non-HTTPS public URL. Set
`BOOKPILE_SERVER_RATE_LIMIT_KEY_SECRET` to a long random deployment secret.

Common lifecycle commands preserve the named volume unless `-v` is explicitly
requested:

```powershell
# Stop PostgreSQL while preserving Server development data.
docker compose -f server\compose.yaml stop

# Recreate/start it later using the same volume.
docker compose -f server\compose.yaml up -d db mailpit
```

Development email is captured at <http://127.0.0.1:8025>. SMTP and the Mailpit
web interface are bound to loopback only. Mailpit must never be used as the
hosted email provider.

Do not use `docker compose down -v` as a routine stop command: `-v` deliberately
deletes the Server PostgreSQL volume. It still cannot affect BOOKPILE Local's
SQLite catalogue, which is outside Docker in the separate Local worktree.
