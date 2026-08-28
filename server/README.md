# BOOKPILE Server foundation

This directory is the isolated beginning of the hosted multi-user edition.
It does not read or modify BOOKPILE Local data.

The repository currently uses two Git worktrees. Run every command in this
document from `C:\Users\Russula\.code\_BOOKPILE_SERVER`. The sibling
`_PERSONAL_LIBRARY_MANAGER` directory is the live Local v1 installation and
must not be used for Server migrations or test databases.

## Current Phase 1 slice

- Environment-based Server configuration.
- SQLAlchemy session boundaries.
- PostgreSQL schema managed by Alembic.
- Minimal `libraries` and `books` tables.
- Read-only catalogue endpoint scoped by library ID.
- Repository and API tests proving that one library cannot read another
  library's catalogue through this slice.

Authentication is intentionally absent. A path library ID is only a temporary
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
docker compose -f server\compose.yaml up -d db
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

The seed script refuses non-development environments, remote hosts, databases
not named exactly `bookpile`, and non-PostgreSQL targets. Its records are not
copied from a Local catalogue.

Do not reuse production credentials or Local catalogue paths in development.

## Safety status

Phase 1's migration and isolation gate passed on 2026-08-28 against PostgreSQL
17 running in Docker Desktop/WSL 2. The test performs an Alembic upgrade,
checks repository and HTTP isolation with two synthetic libraries, and then
downgrades the disposable `bookpile_test` database until no BOOKPILE
application tables remain. Alembic may retain its empty administrative
`alembic_version` table.

The committed password is for loopback-only local development. Hosted and
staging environments must obtain unique secrets from deployment configuration.

Common lifecycle commands preserve the named volume unless `-v` is explicitly
requested:

```powershell
# Stop PostgreSQL while preserving Server development data.
docker compose -f server\compose.yaml stop

# Recreate/start it later using the same volume.
docker compose -f server\compose.yaml up -d db
```

Do not use `docker compose down -v` as a routine stop command: `-v` deliberately
deletes the Server PostgreSQL volume. It still cannot affect BOOKPILE Local's
SQLite catalogue, which is outside Docker in the separate Local worktree.
