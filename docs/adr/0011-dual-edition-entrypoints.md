# ADR 0011: Explicit Local and Server entrypoints

- Status: Accepted
- Date: 2026-09-06

## Context

BOOKPILE Local and BOOKPILE Server now coexist on `main`, but they have
different trust boundaries and runtime data. Local uses the released FastAPI
and SQLite backend under `backend/`; Server uses the authenticated PostgreSQL
backend under `server/`. A branch-dependent frontend entrypoint made it too
easy to build the wrong product and prevented one commit from proving both.

The live Local installation remains in the separate
`C:\Users\Russula\.code\_PERSONAL_LIBRARY_MANAGER` worktree on
`release/local-v1`. It must never be used as a Server test target.

## Decision

1. Keep one frontend workspace and one stable HTML entry. A Vite virtual module
   resolves at build time to either `src/main.local.tsx` or
   `src/main.server.tsx`.
2. Use technical Vite modes `edition-local` and `edition-server`; the reserved
   Vite mode name `local` is deliberately not used.
3. Provide explicit `dev`, `build`, `preview`, and test commands for each
   edition. The unqualified compatibility aliases select Server because active
   development is Server-first.
4. Write optimized output to `frontend/dist/local/` and
   `frontend/dist/server/`. Different titles, dependency graphs, asset hashes,
   and sizes are acceptance evidence that the products were not accidentally
   bundled together.
5. Local proxies `/api` to port 8000 and removes the `/api` prefix, preserving
   its existing backend contract. Server proxies `/api` unchanged to port
   8100. Isolated parallel tests may override those defaults with
   `BOOKPILE_LOCAL_BACKEND_URL` or `BOOKPILE_SERVER_BACKEND_URL` without
   changing committed configuration.
6. Local installation and launch scripts always request the Local build and
   Local output explicitly. They never rely on the compatibility alias.
7. Keep SQLite and PostgreSQL backends, migrations, and test data separate.
   This checkpoint performs no schema migration and does not begin Local ZIP
   import.
8. Preserve historical tag `v1.0.0` and maintenance branch
   `release/local-v1`. Future edition releases use independent tags
   `local-vX.Y.Z` and `server-vX.Y.Z`; no Server release is produced before its
   deployment gates are complete.

## Verification

The automated gate runs both frontend test scopes, lint, both optimized
builds, all Local backend tests against temporary SQLite files, and all fast
Server tests. PostgreSQL integration remains a separate explicitly disposable
database gate. Manual acceptance must finally launch each correct
frontend/backend pairing and identify it before this checkpoint merges.

Acceptance completed on 2026-09-06: Local was identified against a disposable
SQLite catalogue and Server was identified against the preserved development
PostgreSQL volume. The automated result was 11 Local frontend tests, 17 Server
frontend tests, 133 Local backend tests, and 80 fast Server backend tests; the
explicit PostgreSQL integration suite remained a separate gate.

No command in this gate opens, migrates, restores, or writes the populated
Local catalogue.

## Consequences

- A developer can work from one `main` commit without switching branches to
  choose an edition.
- Shared frontend dependencies remain installed together for now; build-time
  entrypoint selection prevents the inactive application from entering the
  active dependency graph.
- A Local source archive may come from the monorepo, but its installer and
  launchers only build and run Local. A deployable Server release remains a
  future, separate artefact.
- Features are still ported deliberately. This change does not imply shared
  databases or interchangeable live runtimes.
