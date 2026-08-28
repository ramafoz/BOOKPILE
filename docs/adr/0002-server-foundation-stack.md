# ADR 0002: Server foundation stack

- Status: Accepted for Phase 1
- Date: 2026-08-28

## Decision

- Python 3.12 or newer and FastAPI remain the backend platform.
- SQLAlchemy 2 provides explicit database sessions and repository queries.
- PostgreSQL is the production database; psycopg 3 is its driver.
- Alembic owns every Server schema migration.
- Pydantic Settings reads configuration from environment variables.
- Pytest exercises services, repositories, API boundaries, and migrations.
- PostgreSQL 17 is the initial development image pin. Upgrades require a
  documented compatibility decision rather than silently following `latest`.
- Node 22 remains suitable for the existing frontend toolchain. A separate
  Server frontend entry point is deferred until the backend boundary is proven.

## Development without Docker

Docker is convenient but is not required to inspect or test the first slice.
Repository and API isolation tests use a temporary in-memory SQLite database,
while the checked-in Alembic migration and Compose definition target
PostgreSQL. PostgreSQL integration tests become mandatory before Phase 1 is
accepted; they may run through Docker, a local PostgreSQL installation, or CI.

## Why this is temporary

SQLite tests provide fast feedback but cannot prove PostgreSQL behavior such as
concurrent transactions, row locking, JSON semantics, or production migration
compatibility. They supplement rather than replace the Phase 1 PostgreSQL gate.

