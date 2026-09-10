# BOOKPILE Server production rehearsal runbook

This is the provider-neutral procedure for rehearsals and the future staging
host. It is **not** permission to publish BOOKPILE yet: real-provider
acceptance, observability and the Spanish staging recovery drill remain gates.

## Package and boundaries

- `server/docker/api.Dockerfile` builds the API as unprivileged UID/GID 10001.
- `server/docker/web.Dockerfile` builds the Server SPA and runs Caddy without
  root privileges.
- `server/docker/Caddyfile` is the only public entry point: it terminates HTTPS,
  serves the SPA and proxies API/health traffic over a private network.
- `server/compose.production.yaml` connects PostgreSQL, one-shot migrations,
  API, email worker, web and an operations-profile backup job. PostgreSQL and
  FastAPI publish no host ports.
- `server/.env.production.example` names required settings but has no usable
  secrets.

Application startup never migrates the schema implicitly. The separate
`migrate` service must succeed before the API starts.

## One-time host preparation

Install Git and a current Docker Engine with its Compose plugin. Check out the
exact approved revision, then create the private configuration:

```bash
cp server/.env.production.example server/.env.production
chmod 600 server/.env.production
```

Replace every example value. Separately copy `.env.backup.example` to
`.env.backup`, mode `600`; API services never receive those secrets. Set the deployment revision to the exact commit;
use the final HTTPS origin and bare allowed hostname; create independent random
secrets of at least 32 characters; and use one new PostgreSQL password in both
the Compose variable and encoded database URL. Never reuse development,
staging or test credentials. Keep API documentation disabled and secure cookies
enabled. `openssl rand -hex 32` creates URL-safe secrets. The real env file is
ignored by Git and must also be protected and backed up as a secret.

Before certificate issuance, point DNS at the host and allow inbound TCP 80/443
only. Never publish 5432 or 8100.

Install and enable the reviewed timers under `server/deploy/systemd` after
following `SERVER_OPERATIONS_AND_SECURITY.md`. Connect failed units to the
selected alert route; timers without observed failures are not monitoring.

## Preflight and build

Run from the repository root:

```bash
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml config --quiet
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml build api web
```

Preflight must fail if a required value is absent. A later pipeline may select
immutable registry tags through `BOOKPILE_API_IMAGE` and `BOOKPILE_WEB_IMAGE`.

## Backup, migrate and start

For an existing environment, first create and verify the Phase 9D database and
object backup according to `SERVER_OPERATIONAL_BACKUP.md`.

```bash
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml up -d db
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml run --rm migrate
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml up -d api email-worker web
```

The API remains unready until PostgreSQL and the configured private-object
adapter both answer. Caddy waits for API readiness.

## Verification

```bash
curl --fail --silent https://books.example.com/health/live
curl --fail --silent https://books.example.com/health/ready
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml ps
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml logs --tail=100 api web
```

Replace the example host. Liveness proves the API process responds; readiness
also proves database and private-object access. Responses identify the deployed
revision. Request logs use generated IDs and route templates while omitting
queries, tokens, IP addresses and library data.

Then perform a staging smoke path: sign in, open a test-owned library, read a
private cover, make one reversible test write and confirm its audit event. Do
not use production member data for smoke tests.

## Rollback and stop

Application rollback selects the previous approved immutable API/web tags and
restarts those services. Do not downgrade the database merely to roll back an
application image. Schema downgrade is a separate decision requiring a verified
backup and migration-specific data-loss review.

```bash
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml up -d api web
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml stop
```

Never use `down -v`: named volumes contain the database, private objects and TLS
state. Total-host-loss recovery remains unproven until the Phase 9F off-site
restore drill.

## Phase 9A local evidence

- Hosted startup rejects unsafe secrets, cookies, origins, documentation,
  trusted hosts and databases.
- Health boundaries, defensive headers and redacted logs are tested.
- 133 Local and 176 Server isolated tests pass.
- The full migration/concurrency gate passes on disposable PostgreSQL 17.
- 11 Local and 30 Server frontend tests, lint and both builds pass.
- Compose and Caddy validate; both pinned images build and declare
  unprivileged runtime users.
