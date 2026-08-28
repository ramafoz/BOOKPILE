# ADR 0001: Separate Local and Server development lines

- Status: Accepted
- Date: 2026-08-28

## Context

BOOKPILE Local v1 is a released, independently installable SQLite application.
BOOKPILE Server will become an invitation-only hosted product with multiple
accounts and libraries. Retrofitting tenancy directly into the released Local
runtime would put the stable application and its existing catalogues at risk.

## Decision

- Tag `v1.0.0` is immutable.
- Branch `release/local-v1` is the maintenance line for critical Local fixes.
- Server development begins on `feature/server-foundation`.
- The working copies are physically separated with Git worktrees:
  - `C:\Users\Russula\.code\_PERSONAL_LIBRARY_MANAGER` stays checked out on
    `release/local-v1` and remains Javier's live personal library.
  - `C:\Users\Russula\.code\_BOOKPILE_SERVER` is checked out on
    `feature/server-foundation` and contains hosted-product development.
- Server code lives under `server/` while the existing `backend/` and
  `frontend/` remain the Local application during the foundation phases.
- Local keeps SQLite. Server targets PostgreSQL and uses Alembic migrations.
- Server business access is library-scoped at repository boundaries from the
  first query, before authentication is implemented.
- The first Server increment is read-only and uses synthetic test data only.
  It never opens `backend/data`, Local backups, or user cover files.

## Consequences

- Local v1 remains downloadable and recoverable while Server changes freely.
- Some behavior will temporarily exist in both Local code and new Server
  services. Porting must be incremental and covered by regression tests.
- Authentication cannot be treated as the tenancy boundary. Repository and
  service methods must require an explicit library identifier even after login
  exists.
- A future Local ZIP import is a conversion process into Server data, not a
  direct replacement of a Server database.
- Server commands, migrations, virtual environments, and disposable databases
  must be created from the Server worktree. The Local worktree's
  `backend/data` and `backend/backups` directories are never Server inputs.

