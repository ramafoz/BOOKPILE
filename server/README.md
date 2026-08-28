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
$env:BOOKPILE_SERVER_TEST_DATABASE_URL = "postgresql+psycopg://bookpile:bookpile-dev@localhost:5432/bookpile_test"
server\.venv\Scripts\python -m pytest server\tests\test_postgresql_integration.py
```

Run PostgreSQL with Docker, when Docker is available:

```powershell
docker compose -f server\compose.yaml up -d db
$env:BOOKPILE_SERVER_DATABASE_URL = "postgresql+psycopg://bookpile:bookpile-dev@localhost:5432/bookpile"
server\.venv\Scripts\alembic -c server\alembic.ini upgrade head
server\.venv\Scripts\uvicorn bookpile_server.main:app --app-dir server\src --reload --port 8100
```

Do not reuse production credentials or Local catalogue paths in development.

## Safety status

The in-memory isolation suite and PostgreSQL migration SQL can be validated
without PostgreSQL. Phase 1 is not accepted until the opt-in PostgreSQL test
also passes against a disposable instance.
