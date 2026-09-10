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
- Minimal `libraries` and `books` tables, now protected by real membership
  authorization rather than a path identifier alone.
- Equal co-Owners and read-only Viewers, with catalogue-only or
  catalogue-and-map Viewer scopes.
- Hashed, expiring, single-use library invitations kept separate from beta
  account-registration invitations.
- Membership management with password reauthentication, explicit consequence
  warnings, final-Owner protection, and structured audit events.
- Reading-perspective selection plus the complete Phase 5A–5C persistence,
  service, API, and catalogue experience for Owner-scoped sessions and
  personal Goodreads records.
- Repository and API tests proving that one library cannot read another
  library's catalogue merely by knowing its UUID.
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
- Phase 2G responsive Server authentication shell for invitation registration,
  verification, login/logout, and password recovery.
- Phase 3 responsive library dashboard for creating/selecting libraries,
  joining through a full invitation URL or raw token, and managing Viewer
  scope or equal co-Ownership.
- Phase 4A shared catalogue schema: full nullable book metadata, extensible
  ordered contributor roles, translation/language fields, optional physical
  dimensions, hierarchy, and fixed-precision visual layout. Composite foreign
  keys prevent cross-library parent relationships.
- Phase 4B library-scoped catalogue services and responsive frontend: complete
  shared metadata, ordered contributors, strict validation, simple and
  advanced search, metadata options, sorting, pagination, read-only details,
  Owner-only writes, CSRF, explicit deletion confirmation, and audit events.
- Phase 4C authenticated private covers: Owner-only upload, replacement, and
  removal; Owner/Viewer reads; safe image validation and WebP re-encoding;
  opaque filesystem objects; no-store delivery; rate limiting; and audit.
- Phase 4D physical-library slice: Owner-maintained hierarchy and layout,
  scoped map reads, responsive camera and inspection, catalogue-row locations,
  per-book placement, and transactional visual rearrangement with read-only
  previews, stale-revision protection, proportional geometry, and audit.
- Phase 5A personal-reading foundation: reversible additive session and sparse
  personal-book-record tables, database-enforced date shapes and active/unknown
  uniqueness, plus pure chronology, state, inclusive-duration, reading-rate,
  and active-counter rules. That schema increment itself exposed no API.
- Phase 5B scoped reading API: members can inspect an Owner perspective;
  authenticated Owners can mutate only their own sessions and Goodreads URL;
  Viewers remain read-only; copy locking and database uniqueness prevent two
  simultaneous readers; writes require CSRF and emit library audit events.
- Phase 5C perspective-aware catalogue: personal status actions, read-only
  cross-Owner history, self-only history/Goodreads management, suggestions,
  rereading-aware counters, and optional completed/unknown/active reading data
  during Single or Batch Add.
- Phase 5D–5E map/statistics integration and compatibility cleanup: shared
  active-reading custody, perspective-aware colours and inspection, complete
  reading statistics, and guarded removal of the obsolete shared Goodreads
  field.
- Phase 6A shared-loan foundation: additive `0014_shared_loans`, one active
  loan per physical copy, tenant-safe composite ownership, guarded rollback,
  and pure chronology, overdue, ordering, and custody-precedence rules. That
  schema increment itself exposed no API or frontend.
- Phase 6B shared-loan services and APIs: Owner lifecycle and full history,
  Viewer-safe projections that cannot serialize borrower/notes, catalogue
  overview, tenant scope, CSRF, redacted audit, Book-row locking, and
  reading-start exclusion.
- Phase 6C–6D accepted loan experience: responsive Owner management and
  Viewer-redacted inspection, atomic Single/Batch Add loans, catalogue filters,
  On-loan map precedence, retained locations, suggestion exclusion, and shared
  non-sensitive statistics. Phase 6E Local-contract comparison and all final
  gates pass, and Phase 6 is merged into `main`.
- Phase 7A–7B storage/profile foundation: deterministic logical-byte accounting,
  entitlement-ready co-Owner allocation, additive migration `0015`, exact
  backfill, database-guarded profile privacy and scoped authenticated projections.
  Phase 7C applies one locked quota transaction boundary to all shared writes,
  membership changes and cover-object compensation, including a PostgreSQL race
  gate. Phase 7D adds the responsive private account/profile workspace, grouped
  privacy, authenticated member-profile projections, profile-image processing,
  password/session controls, Owner library-settings navigation, and non-numeric
  storage contribution/total bars. Phase 7E adds recoverable shared-library
  deletion; 7F adds email-only recoverable account deletion; 7G adds earned
  beta account invitations and empty-library map onboarding. Phase 7 final
  compatibility, migration, build and user-acceptance gates pass.

The authentication and library-membership foundations are complete through
Phase 3, and the shared catalogue, private-cover, and physical-library
foundations are complete through Phase 4D. Catalogue access requires an
authenticated membership; a library ID is never authorization. The Server
edition is not production-ready because real storage/email provider acceptance,
operational monitoring and staging recovery drills are not complete. Phase 9A
provides strict hosted configuration, health boundaries, privacy-safe request
logs, CI, pinned non-root images and a private-network Caddy/Compose rehearsal
topology; see `SERVER_PRODUCTION_RUNBOOK.md`. Owner-only Server
ZIP export and explicit-mapping restore are implemented and accepted with bounded
inspection, atomic quota enforcement and object compensation. Phase 8 is
complete. Application-level storage quota is implemented;
operational storage, monitoring and deployment controls remain production work.

Phase 9B's provider-neutral private S3 adapter and guarded filesystem migration
are implemented without changing authenticated media URLs. Production still
waits for provider acceptance and staging reconciliation; see
`SERVER_PRIVATE_OBJECT_STORAGE.md`.

Phase 9C replaces request-bound hosted email with an encrypted transactional
PostgreSQL outbox and a separately supervised worker. Development deliberately
keeps immediate Mailpit delivery. See `SERVER_EMAIL_OUTBOX.md`.

Phase 9D adds a separately credentialed, non-root backup image, encrypted
off-site snapshots, compliance retention and empty-target disaster recovery.
The complete local PostgreSQL/S3 rehearsal passes; provider and staging gates
remain. See `SERVER_OPERATIONAL_BACKUP.md`.

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

In a second terminal, start the isolated Server frontend:

```powershell
cd frontend
npm ci
npm run dev:server -- --host=127.0.0.1
```

Open <http://127.0.0.1:5173>. Vite proxies `/api/v1` to the Server backend on
port 8100. Mailpit captures verification and recovery links during development.

The same frontend workspace can build both products explicitly without
sharing runtime data:

```powershell
npm run build:server
npm run test:server
```

Server output is written to `frontend/dist/server/`. Local has a separate
entrypoint, proxy, tests, and `frontend/dist/local/` output; this Server setup
never starts the Local SQLite backend.

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
These account invitations create eligibility to register but never grant
access to a library. After registration, an existing Owner creates a separate
library invitation from the Server dashboard. Library invitations can grant
either catalogue-only Viewer access, catalogue-and-map Viewer access, or equal
co-Ownership. The join field accepts either the displayed full link or its raw
token.

Account deletion is likewise separate from library deletion. It requires
reauthentication and is blocked while the account owns any active library.
BOOKPILE sends the registered address a random, single-use recovery link before
committing deletion; if delivery fails, deletion is rolled back. PostgreSQL
stores only the token hash. The link is the sole recovery route for 48 hours,
after which cleanup permanently removes the account and its remaining personal
objects. Signing in never discloses whether an account is in deletion quarantine.

The seed script refuses non-development environments, remote hosts, databases
not named exactly `bookpile`, and non-PostgreSQL targets. Its records are not
copied from a Local catalogue.

Do not reuse production credentials or Local catalogue paths in development.

## Catalogue API

All routes require an authenticated library membership. A Viewer may use the
GET routes; an Owner may additionally use POST, PUT, and DELETE with a valid
CSRF token.

- `GET /api/v1/libraries/{library_id}/catalogue`
- `GET /api/v1/libraries/{library_id}/catalogue/metadata-options`
- `GET /api/v1/libraries/{library_id}/catalogue/{book_id}`
- `POST /api/v1/libraries/{library_id}/catalogue`
- `PUT /api/v1/libraries/{library_id}/catalogue/{book_id}`
- `DELETE /api/v1/libraries/{library_id}/catalogue/{book_id}`
- `GET /api/v1/libraries/{library_id}/catalogue/{book_id}/cover`
- `PUT /api/v1/libraries/{library_id}/catalogue/{book_id}/cover`
- `DELETE /api/v1/libraries/{library_id}/catalogue/{book_id}/cover`
- `GET /api/v1/libraries/{library_id}/catalogue/{book_id}/reading`
- `GET /api/v1/libraries/{library_id}/reading-overview`
- `POST /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/sessions/start`
- `POST /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/sessions/{session_id}/finish`
- `DELETE /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/sessions/{session_id}/cancel`
- `POST /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/sessions/historical`
- `PUT|DELETE /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/sessions/{session_id}`
- `GET /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/goodreads`
- `PUT /api/v1/libraries/{library_id}/catalogue/{book_id}/reading/goodreads/me`

Updates are complete replacements rather than partial patches. The client
must send the complete editable bibliographic record and contributor order.
Delete requests must repeat the exact current title. Covers use independent
multipart endpoints so a failed optional image cannot invalidate a saved book.
Physical positions, readings, and loans are intentionally not part of these
payloads.

## Safety status

The migration and isolation gate now upgrades through migration
`0012_personal_readings` against PostgreSQL 17. It checks catalogue and
membership isolation, identity/session/account-invitation/library-invitation
records, concurrent invitation consumption, atomic rate limiting, final-Owner
protection, scope changes, reading perspectives, shared metadata constraints,
cross-library physical relationships, contributor normalization, preservation
of pre-Phase-4A books, Phase 4B service writes and ordered contributors, and
private covers, revisioned layout, physical projection, explicit shelf
geometry, fallbacks, support rules, reading-session shape and uniqueness,
concurrent starts for one physical copy, personal-book records, and each incremental rollback. It then downgrades
disposable `bookpile_test` until no BOOKPILE application tables remain.

Phase 5C additionally passes the frontend unit suite, lint and Server build;
desktop/mobile Owner and Viewer acceptance was completed on 2026-09-07.
Alembic may retain its empty administrative `alembic_version` table.

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

If the browser remains on **Opening BOOKPILE...**, first verify that the Docker
PostgreSQL service is running. Restart the Server Vite process after changes to
Vite configuration or edition entrypoints; an already-open tab cannot repair a
stale development process by itself.
