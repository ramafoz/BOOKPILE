# BOOKPILE Server Phase 9 — Production operations

## Objective

Phase 9 turns the accepted invitation-only Server application into a
reproducible, recoverable service. It does not change BOOKPILE Local and does
not make the service public merely because containers can be built. The phase
ends only after a fresh Spanish-hosted environment has been restored from
backups and its measured recovery result is documented.

## Fixed boundaries

- The public browser sees one HTTPS origin. The reverse proxy serves the Server
  SPA and forwards `/api/v1` to FastAPI over a private network.
- FastAPI and PostgreSQL are never exposed directly to the public internet.
- PostgreSQL may initially share the VPS, but encrypted verified backups leave
  that failure domain.
- Covers and profile images use private S3-compatible storage before production;
  clients continue to read them only through authorized API endpoints.
- Secrets and provider credentials never enter Git, images, frontend bundles,
  logs, or backup manifests.
- Schema migration is a separate guarded deployment step. Application startup
  never performs an implicit migration.
- Staging and production use different databases, buckets, email credentials,
  cookie namespaces, secrets, and domains.

## Delivery slices

### 9A — reproducible runtime and configuration foundation

Status: implementation and local gates complete. The first IONOS staging-host
deployment passed explicit migration, HTTPS liveness/readiness and an
authenticated library write on 2026-09-13/14. Scheduled operations, rollback
and recovery evidence remain in 9F. Commands are in
`SERVER_PRODUCTION_RUNBOOK.md`.

- Add production startup validation, trusted-host/origin enforcement, secure
  headers, request IDs, and non-sensitive structured request logs.
- Separate liveness from readiness; readiness verifies PostgreSQL and the
  configured private-object adapter.
- Build the API and static Server SPA as pinned, non-root container images.
- Provide a provider-neutral reverse-proxy/Compose rehearsal topology with only
  ports 80/443 public.
- Add CI gates for Local, Server, PostgreSQL migrations, frontend tests, lint,
  and both edition builds.

Gate: a production-like stack builds reproducibly, rejects unsafe configuration,
and reports unavailable until both database and private storage are usable.

Completed locally:

- Hosted startup rejects development secrets, insecure cookies, non-HTTPS
  origins, public API docs, wildcard/unmatched hosts and non-PostgreSQL data.
- Request IDs, privacy-safe route logs, defensive headers and distinct
  process/dependency health checks are implemented and tested.
- Pinned non-root API/web images and the private-network Caddy/Compose topology
  build and validate; migrations are an explicit one-shot prerequisite.
- CI gates Local/Server Python, both frontend editions, lint, PostgreSQL
  migrations and both production images.

The remaining clean-host rehearsal belongs to 9F. It does not block 9B.

### 9B — private S3-compatible object storage

Status: provider-neutral implementation and simulated corruption/migration
gates complete. A private Dinahosting staging bucket passed authenticated
put/stat/read/list/delete, metadata integrity and anonymous-access rejection on
2026-09-13. One private object also passed the real encrypted backup/restore
drill. The 2026-09-15 deep staging reconciliation found one expected/stored
object and zero missing, mismatched or orphaned objects. Dinahosting cannot
issue a distinct read-only credential for the same bucket. The operator
accepted write-capable application-key reuse for the initial private beta on
2026-09-16, with explicit residual risk and reassessment triggers;
see `SERVER_PRIVATE_OBJECT_STORAGE.md`.

- Add an adapter selected by configuration without changing object keys or API
  URLs.
- Require TLS, a private bucket, explicit region/endpoint, bounded timeouts, and
  least-privilege credentials.
- Add streaming reads, verified writes, compensation, inventory/checksum audit,
  orphan detection, and a rehearsed filesystem-to-object-store migration tool.
- Choose and contract the Spanish storage provider only after price, DPA,
  location, egress, lifecycle and export checks.

Gate: an isolated bucket round trip and inventory reconcile every database
object exactly; interruption leaves the active reference valid.

### 9C — durable transactional email

Status: encrypted transactional outbox, leased worker, bounded retries,
delivery-relative recovery windows and local/CI gates complete. Authenticated
implicit TLS through Dinahosting delivered and completed a real account
verification on 2026-09-14. A real password-reset email, one-time link and
new-password sign-in passed on 2026-09-16; the old password was rejected.
The complete verification, password-reset and deletion-recovery cycle passed
with real disposable staging accounts on 2026-09-18. Controlled isolated SMTP
failure then proved rescheduling and successful second-attempt delivery, a
terminal `FAILED` row, aggregate operations failure, external `DOWN` paging,
manual recovery and the external `UP` notification. See
`SERVER_EMAIL_OUTBOX.md`.

The cross-purpose presentation and delivery-hardening implementation now adds
multipart text/HTML templates without remote tracking, standards-compliant
automated-message headers and persisted privacy-safe SMTP acceptance receipts.
Local server acceptance passes. Staging migrated to
`0022_email_delivery_receipts` and exercised every emitted template on
2026-09-18. Each final message returned SMTP `250`, retained its signed subject,
contained no remote resources or tracking and passed SPF, DKIM and DMARC.
Dinahosting disabled the outbound antispam filter whose post-signing subject
rewrite had invalidated DKIM. One authenticated verification message was placed
in Gmail spam while reset and recovery reached the inbox; this residual
receiver-side reputation signal will be monitored during the private beta.

- Replace request-blocking SMTP sends with a PostgreSQL outbox and a separate
  retrying worker.
- Configure authenticated TLS delivery, deterministic message identity,
  exponential retry, terminal failure visibility and provider-safe logging.
- Cover verification, password reset, deletion recovery and operational alerts.

Gate: provider outage never rolls back an accepted domain transaction or loses
the queued email; retries do not create uncontrolled duplicates.

### 9D — backup, restore and retention automation

Status: provider-neutral implementation and a complete local PostgreSQL 17/S3
recovery rehearsal pass. Backblaze B2 EU Central accepted a versioned
COMPLIANCE probe, rejected premature deletion and allowed verified deletion of
that exact version after expiry. On 2026-09-14, the final bucket/key created
and independently verified a real encrypted database-plus-object backup,
restored 36 tables and the object into isolated disposable targets, and a
systemd oneshot created a second verified backup. Final lifecycle expiry,
alerting and measured RPO/RTO remain open; see `SERVER_OPERATIONAL_BACKUP.md`.

- Produce encrypted PostgreSQL custom dumps and private-object inventories to
  off-site storage on a schedule.
- Define retention, deletion-tombstone handling, key custody, integrity checks,
  restore tooling and immutable audit evidence.
- Keep operational backups outside user quota and expire inaccessible deleted
  data within the documented 30-day ceiling.

Gate: a clean database and bucket restore reproduce expected counts, hashes,
memberships and application invariants.

### 9E — edge security, observability and scheduled operations

Status: complete in staging. Provider-neutral edge limits, aggregate health
commands, retention maintenance, systemd schedules, privacy-safe email events,
dependency update
automation and the administration boundary are implemented. The active IONOS
external IPv4 firewall policy now allows only incoming TCP 22/80/443, and an
external backup alert reached the operator. External heartbeats now cover the
15-minute aggregate operations/outbox check, daily private-object reconciliation
and 15-minute host-capacity thresholds. An EU-hosted Sentry project captured a
privacy-scrubbed controlled server exception and delivered the operator alert
on 2026-09-17. Its external uptime monitor now also exercises public readiness;
see `SERVER_OPERATIONS_AND_SECURITY.md`.

- Finalize automatic HTTPS, firewall policy, proxy rate limits, body/time
  limits, dependency scanning and security update policy.
- Add structured application/proxy logs, metrics, alerting, disk/capacity
  thresholds, error reporting and pruning/finalization jobs.
- Document the separate `SYSTEM_ADMIN` and break-glass boundaries before any
  administration UI is exposed.

Gate: alerts and runbooks are exercised without exposing private library,
borrower, token or credential data.

### 9F — Spanish staging deployment and recovery drill

The dated shortlist, recommended separation of failure domains and unresolved
contracting decisions are in `SERVER_STAGING_PROVIDER_DECISION.md`.
The individual-account and EU-boundary decisions are accepted. Dinahosting
manages `bookpile.gal`, active private objects and transactional email;
`staging.bookpile.gal` runs on the IONOS rehearsal VPS. Provider-specific
environment templates, purchase safeguards and the remaining evidence sequence
are in `SERVER_STAGING_PROVISIONING_CHECKLIST.md`. Initial provisioning and the
first authenticated smoke path, encrypted off-site backup, isolated restore and
backup/freshness scheduling, operations alerting, transactional-provider
acceptance and isolated SMTP fault tests have passed. Measured disaster recovery
remains open.

- Select providers and domain after comparing full recurring cost, VAT,
  resources, data location, DPA/subprocessors, backup, support, scaling and exit.
- Provision staging from an empty host using the checked-in artefacts.
- Rehearse preflight, backup, migration, rollout, health verification, rollback,
  total-host loss and provider export.

Gate: measured RPO/RTO, costs, gaps and recovery evidence are recorded.

### 9G — production-readiness review

- Close the threat model, unresolved operational decisions, documentation and
  release checklist.
- Verify that production data cannot be reached from Local, test, CI or staging.
- Obtain explicit go/no-go approval before Phase 10 invitations.

## Initial service-level targets

These are beta engineering targets, not a public SLA:

- Scheduled database backup interval (RPO target): at most 24 hours initially.
- Recovery drill target (RTO): restore a small beta dataset within 4 hours.
- Library/account deletion recovery: existing 48-hour product window.
- Inaccessible data in operational backups: no longer than 30 days.
- Readiness must fail on database or object-storage loss; liveness must remain
  independent so the orchestrator can distinguish dependency failure from a
  dead API process.

Targets may be tightened after measured staging drills.

## Decisions deliberately deferred to later slices

- Exact paid/free entitlement model; the current 100 MB entitlement remains a
  configurable application rule.
- Whether production PostgreSQL later moves to a managed service.
- Any public catalogue, social graph or support access to private data.

