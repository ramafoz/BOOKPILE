# BOOKPILE master work plan

Status date: 2026-10-18

This is the single authoritative source for BOOKPILE delivery status, remaining
work and release gates. A task is complete only when its checkbox is marked and
the evidence named by that task exists. Historical plans under `docs/old/` are
context only. ADRs define accepted architecture; runbooks define procedures;
neither creates an additional work queue.

## 1. Status rules

- `[x]` means the implementation, automated checks and required acceptance
  evidence all exist.
- `[ ]` means at least one required result is absent. Partial work does not
  change the checkbox.
- `**DECIDED:**` records a binding product or architecture choice. It is not a
  completion marker; every implementation and acceptance obligation created by
  that decision remains unchecked in sections 4 through 12 until evidenced.
- Every completion change must name a commit or deployed revision and the
  retained evidence. A statement such as "works" without evidence is not a
  closure.
- A newly discovered release-blocking task must be added here before work on it
  starts. It must not be tracked only in a PR, ADR, chat or external checklist.
- Production may open only when every task in sections 4 through 12 is complete
  and the final go/no-go is recorded. Labels inside those sections are
  explanatory only and cannot weaken this rule. Section 13 is explicitly
  post-beta and is the only non-blocking task section.

## 2. Fixed product and operational decisions

- **DECIDED:** The invitation-only beta has ten launch languages: English,
  Galician, Spanish, Portuguese, Catalan/Valencian, Italian, Basque, French,
  Aranese Occitan and Simplified Chinese.
- **DECIDED:** The beta storage entitlement is exactly `100_000_000` bytes per
  account (decimal 100 MB). Entitlements remain rows in
  `account_storage_entitlements`, so a future operator may assign different
  limits or plan codes without changing catalogue ownership semantics.
- **DECIDED:** Staging and production contain independent databases, object
  buckets, backup repositories, SMTP credentials, monitoring projects, secrets
  and cookies. No database, account, library, book or object is copied from
  staging as part of deployment.
- **DECIDED:** A portable Server ZIP may be exported by an authorized Owner in
  staging and imported by an authorized Owner in production through the normal
  guarded import flow. This is user-directed data portability, not environment
  cloning.
- **DECIDED:** Production receives the same immutable application image digests
  already accepted in staging. Environment configuration and secrets differ;
  code and image contents do not.
- **DECIDED:** A web `SYSTEM_ADMIN` console is a production blocker. It is a
  separate authorization domain and never grants library membership or implicit
  access to private catalogues, maps, covers, readings, loans, exports or email
  bodies.
- **DECIDED:** Raw host, Docker, Caddy and application logs remain host-side. The
  admin console exposes normalized, minimized security and operational events
  and may reveal one retained client-IP field only through the mediated,
  incident-bound control in section 6. It does not expose raw logs, a shell, an
  arbitrary log reader, a filesystem browser or a secret viewer.
- **DECIDED:** The general API IP limit does not require representative public
  traffic in staging. Its rollout gate is deterministic: automated concurrency
  tests, a bounded observe-mode rehearsal, enforce-mode rehearsal, normal
  functional use and a deep operational check.

## 3. Accepted baseline

- [x] BOOKPILE Local v1 is independently tagged, distributable and recoverable.
- [x] Server phases 1-8 are implemented, including identity, tenancy,
  Owner/Viewer roles, private covers, map, readings, loans, quota, deletion,
  Local ZIP import and portable Server export.
- [x] The ten launch languages are implemented and manually accepted. The
  owner has accepted language switching, translated interface behaviour and
  staging use; internationalization implementation is closed.
- [x] Staging is HTTPS-deployed with PostgreSQL, private object storage,
  transactional email, monitoring, scheduled maintenance and deep integrity
  checks.
- [x] Phase 9D is closed: encrypted backups, restore, 29-day retention and
  exact-version permanent expiry are proven.
- [x] Staging deployment performs preflight, optional/normal backup, immutable
  revision tagging, explicit migration, service recreation, public health
  checks, deep checks and assisted application rollback information.
- [x] Defensive D1 inventory, D2 trusted client identity and the implemented D3
  privacy-minimized request logging/scanner responses are accepted.
- [x] Costly-operation limits and renewable fenced leases are enforced for
  import preflight, import consolidation and portable export by user and
  library. Observe/enforce rehearsals and normal use passed at revision
  `6495d21b492dbdcaa55bf6aca0e00cf45483887e`.
- [x] The general `/api/*` IP ceiling is enforced in staging at revision
  `b3700d2882fcde5c08a0ea69e585529880eaec06`. Observe and enforce rehearsals,
  privacy checks, excluded traffic, concurrent-worker decisions, normal use and
  the deep operational check passed on 2026-10-18.

## 4. Defensive security programme

Every item in this section is a **production blocker** unless explicitly marked
otherwise.

### D3-L — Log retention and safe investigation

- [x] Define one retention table covering Caddy edge events, application
  request events, security events, journald, Sentry and immutable admin audit.
  The table records fields retained, purpose, exact duration, deletion method,
  access role and legal-policy reference.
- [x] Configure strict time-based expiry for the active Caddy log. Prove with a
  disposable dated fixture that records older than the configured duration are
  absent after rotation while newer records remain readable.
- [x] Bound journald by both time and disk use; capture `journalctl --disk-usage`
  and effective configuration before and after a controlled service restart.
- [x] Verify that no retained event contains cookies, authorization headers,
  CSRF values, reset/invitation tokens, request bodies, email content, object
  keys or catalogue data.
- [ ] Document and test the host-only procedure for access to raw log files.
  Separately test the console's mediated reveal of one retained client-IP field
  from one normalized security event. Both paths require operator, reason,
  incident, timestamp and result in the immutable admin audit; the console path
  must not permit raw-log access, bulk IP listing, arbitrary search or export.

Evidence: committed retention table and runbook; staging rotation transcript;
redaction tests; one audited raw-evidence access rehearsal.

Retention-table evidence: commit `62a68f9` adds the binding field, purpose,
duration, deletion, role and legal-policy matrix. Staging revision
`a40add206581940bf3b386d4e2ae7a41a040873a` installed the host policy with
`MaxRetentionSec=14day`, `SystemMaxUse=512M`, `SystemKeepFree=1G`,
`SystemMaxFileSize=64M` and `MaxFileSec=1day`; controlled restart, rotation and
vacuum reduced journal use from 575.7 MiB to 188.0 MiB. All four long-lived
containers then reported the `journald` driver. The isolated deployed-image
Caddy rehearsal returned time rotation, legacy-roll migration, retained-new
fixture and expired-old-fixture results as true. The isolated PostgreSQL
rehearsal retained the error class while proving the synthetic private value
and SQL statement absent. Automated request-log fixtures cover cookies,
authorization and CSRF headers, reset/invitation tokens, bodies, email content,
object keys and catalogue values. The first staging query exposed that the
minimized Python logger had no production output handler; acceptance remained
open until corrective revision
`af10471343da73687cf7e4fd9b1139cd634f93d8` emitted real `http_request` rows
through journald with route templates, keyed 16-hex client pseudonyms and no
raw address, query, header, body or private catalogue content. The final deep
check reconciled 440 expected and stored private objects with zero missing,
mismatched or orphaned objects. The remaining raw-evidence checkbox stays open:
its console half depends on A3/A4 and cannot be accepted by host evidence alone.

### D4-G — General API IP ceiling

- [x] Change `BOOKPILE_SERVER_GENERAL_API_LIMIT_MODE` from `observe` to
  `enforce` in staging and recreate only the API.
- [x] In a fresh fixed window, run a bounded 650-request rehearsal and prove
  that requests through the threshold retain their normal response, excess
  requests return generic `429` with `Retry-After`, exactly one
  `rate_limit_blocked` event is emitted and no raw IP is stored in the bucket or
  event.
- [x] Complete normal login, catalogue, cover and map use after the rehearsal;
  prove `/health/live`, `/health/ready`, frontend and static assets are not
  counted; run the deep operational check.
- [x] Exercise two API workers concurrently and prove that their combined
  decisions cannot exceed the configured shared threshold.

Evidence: command output, event/bucket status, response headers, revision and
deep-check result. The enforce rehearsal returned 600 normal `404` responses
and 50 generic `429` responses in ten seconds; an additional blocked request
carried `Retry-After: 51`, `Cache-Control: no-store` and a request ID. The
shared bucket reached 651, its key was a 64-character HMAC, and exactly one
revision-labelled event with a null `ip_address` was written. Three live and
ready checks, the frontend and a built JavaScript asset left the bucket at 80;
normal login, catalogue, cover and map use passed. Both Uvicorn workers were
running, and the PostgreSQL integration gate starts two independent operating-
system processes, gives each its own configured API middleware stack and
database pool, releases both requests simultaneously against the same
`general_api_ip` key, and requires one `404` plus one generic `429`. The deep
check accounted for all 435 private objects with zero discrepancies.

### D4-M — Authenticated and library mutation ceilings

- [x] Implement a PostgreSQL-backed `240/15 minutes` ceiling per authenticated
  user for state-changing API operations, independently configurable as
  `off/observe/enforce`.
- [x] Implement a PostgreSQL-backed `600/15 minutes` ceiling per authorized
  library for state-changing operations. An unauthorized or nonexistent
  library identifier must not consume a library bucket.
- [x] Prove atomic decisions across two workers, fixed-window reset,
  `Retry-After`, generic `429`, fail-closed generic `503`, HMAC key privacy and
  independent rollback switches.
- [x] Prove in one correlated rehearsal that two users behind one IP receive
  independent user decisions, two co-Owners in one library receive one shared
  library decision, and both users' requests consume the same IP bucket.

Evidence: migration if required, tests, staging observe/enforce rehearsal and
normal multi-owner functional test. The implementation uses the existing
PostgreSQL/HMAC bucket schema and therefore needs no migration. User and
library policies have separate mode switches and default to `off`. A matched
route dependency authenticates first and uses an explicit reviewed registry so
only state-changing routes count by user. A path-addressed library counts only
after the route's required member or Owner role is confirmed; public requests,
safe methods, read-only POST routes, absent libraries and unauthorized users do
not consume a library bucket. The PostgreSQL gate starts independent processes
with separate dependency stacks and pools for both user and co-Owner/library
races. Staging revision `f306f30363358363d17d561268b548c2b908a8ff` passed the
bounded observe rehearsal with exactly one correlated
`rate_limit_observed` event at 241 user attempts and 601 library attempts, then
passed the enforce rehearsal with exactly one correlated
`rate_limit_blocked` event at each threshold. A normal functional test with two
co-Owners behind the same client IP produced independent real user buckets
with counts 3 and 5 and one shared library bucket with count 4; every stored
mutation key was a 64-character HMAC rather than a raw identifier. Both
mutation policies are now in `enforce` on staging. Normal use remained correct
and the final deep operational check accounted for all 435 private objects
with zero discrepancies. This accepts the user and library portions of the
final gate. The correlated shared-IP rehearsal then recorded the same
`general_api_ip` HMAC bucket tag and the same
`2026-10-19 22:04:00.527734+00` window after each account acted: its count rose
from 6 to 13 by `22:04:21.839147+00`. This proves that the independent user
decisions and shared library decision coexist with one combined IP decision
for the two accounts. D4-M is accepted.

### D4-S — Specific operation ceilings

- [x] Add the authorized-library bibliographic lookup ceiling of `360/hour`
  alongside the existing client-IP and user controls.
- [x] Add the authorized-library cover-upload ceiling of `120/hour` alongside
  the existing `30/hour/user` control.
- [x] Add rearrangement preview/apply observation at `120/minute/user` and
  `240/minute/library`; enforce only after automated normal interaction remains
  below 25% of both thresholds.
- [x] Prove that rejected lookups, uploads and rearrangements leave no database
  or object residue and return only generic policy responses.

Evidence: focused tests, staging status/events, one accepted normal workflow for
each operation and one bounded blocking rehearsal. Revision
`11ceb788b548fd76062df1638014e0171224376e` uses the shared PostgreSQL/HMAC
bucket infrastructure and independent `off/observe/enforce` switches; no
migration was required. Focused tests prove authorization precedes charging,
blocked provider calls and rearrangements cannot mutate state, blocked cover
uploads leave neither metadata nor private objects, and decision failures
return only generic `429` or fail-closed `503` responses. Observe rehearsal
`1186b064-5f1b-4bf7-aeae-d966bfbef3c6` emitted exactly one correlated
`rate_limit_observed` event for each new scope at 301 IP lookups, 361 library
lookups, 121 library cover uploads, 121 user rearrangements and 241 library
rearrangements. Normal staging use recorded one user, IP and library ISBN
lookup; four user and four library cover-upload attempts; and two user plus
three library rearrangement attempts. The rearrangement counts were below 25%
of both thresholds and no normal operation returned `429` or `503`. All three
policies were then changed to `enforce`. Blocking rehearsal
`85f1877d-e092-4413-b4ab-ff99660d4ecc` produced exactly one correlated
`rate_limit_blocked` decision for every new scope. The final deep check
accounted for all 440 private objects with zero missing, mismatched or orphaned
objects. D4-S is accepted.

### D4-O — Abandoned private-object recovery

- [x] Implement a dry-run command that lists only private objects absent from
  committed metadata, older than a configured grace period and not protected
  by an active import/export lease or in-flight job.
- [x] Make deletion opt-in, bounded per run, exact-key based and auditable. A
  database or lease decision failure must stop deletion.
- [x] Run dry-run against staging, inject one disposable orphan, prove detection
  without touching any expected object, delete only the disposable orphan and
  pass deep reconciliation.
- [x] Keep the accepted 24-hour/25-object cleanup in persistent `enforce` mode
  under the hourly systemd timer and record a successful scheduled-path run.
- [x] Install the distinct external hourly-maintenance dead-man switch, prove a
  success ping and operator notification test, and retain daily deep
  reconciliation as the non-zero orphan-backlog alert.
- [x] Document and prove the independent disable switch: setting only
  `BOOKPILE_SERVER_PRIVATE_OBJECT_ORPHAN_CLEANUP_MODE=off` stops orphan recovery
  without disabling unrelated maintenance.

Evidence: tests for race/failure/grace-period cases and the staging injection,
cleanup and deep-check transcript. The implementation defaults to `off`, uses
a 24-hour grace and a 25-object batch limit, fails closed on unknown object age
or unavailable coordination, revalidates every candidate immediately before
exact-key deletion under PostgreSQL write-excluding decision locks, and records
only keyed object HMACs. Staging dry-run first reconciled 440 expected and 440
stored objects. Rehearsal object HMAC `e3b45afb8d66...f6a2ce77` was detected but
rejected during its one-hour acceptance grace, later became the sole candidate,
and was the sole deletion under a one-object cap. Deep reconciliation returned
440 expected, 440 stored, zero missing, mismatched or orphaned, and healthy.
Persistent `enforce` then completed through the hourly systemd service with
zero candidates or removals; the timer remained scheduled for minute 11. The
distinct `BOOKPILE staging - mantenimiento horario` UTC cron check uses a
30-minute grace. At 2026-10-24 10:45:51 UTC the complete systemd path recorded
both maintenance and protected `ExecStartPost` ping as `0/SUCCESS`; Healthchecks
turned green and the operator mailbox received its notification test. Daily
deep reconciliation remains the independent non-zero backlog alert. D4-O is
accepted and active in staging.

### D5 — Aggregate detection and alerting

- [x] Produce aggregate metrics for `429`, `503`, lease conflicts, scanner
  probes, temporary bans, repeated validation failures and `5xx`, labelled by
  policy/scope/revision but never by raw identity or request content.
- [x] Define exact warning and critical thresholds, alert destination, grouping
  window, recovery notification and owner for every metric.
- [x] Trigger one disposable warning and one disposable critical alert in
  staging; prove delivery, deduplication and recovery without exposing private
  data.
- [ ] Expose the same sanitized aggregates in the `SYSTEM_ADMIN` console.

Evidence: metric catalogue, alert configuration and alert/recovery receipts.

Staging metric-source acceptance on 2026-10-28 deployed revision
`3aa18f68be231be8530a1a81bad8c9c1202338ad` after verified backup
`df837c4d-3eeb-43c7-9872-5e3b659ef4af`. The root-owned 15-minute systemd
collector passed unit verification and two manual runs with `0/SUCCESS`; its
timer remained scheduled. The first run emitted all seven required metric
families with aggregate-only empty totals. One controlled `/.env` probe then
returned `404` and the next run emitted exactly one `scanner_probes` event with
fixed scope `scanner_probe` and the deployed revision. An independent parser
confirmed the exact seven-name set, 15-minute window, validation threshold of
five and absence of client keys, raw addresses, authorization/cookie/query
fields and user, library or object identifiers. Deep reconciliation remained
healthy at 438 expected and 438 stored objects with zero missing, mismatched or
orphaned objects. A zero `temporary_bans` total records that D6 has not enabled
that policy; it does not claim an active ban.

Staging alert acceptance on 2026-10-29 deployed revision
`b7d46d577c387e237151d1a06792369be2e56e2d`. The scheduled collector and
evaluator completed with `0/SUCCESS`, emitted all seven aggregate families and
reported healthy success signals to both dedicated Healthchecks channels. A
disposable warning was delivered exactly once; repeating the same warning
produced no second email. A disposable critical alert was likewise delivered
exactly once and produced no duplicate when repeated. Warning and critical
recovery notifications were received, and both checks were green after the
fixture returned to healthy. Inspection found none of the prohibited private
fields, deep reconciliation remained healthy and normal authenticated catalogue
use passed. The synthetic fixture changed no application or security data. The
future `SYSTEM_ADMIN` aggregate view is the only remaining D5 task.

### D6 — Edge defence before Python

- [ ] Make Caddy emit mutually exclusive fixed labels `health_class=live`,
  `health_class=ready` and `health_class=other`, deleting original URI and query
  data; prove one fixture cannot match two classes.
- [ ] Rehearse the public health policies independently in dry-run: more than
  `120 /health/live` requests from one validated client IP in 60 seconds and
  more than `30 /health/ready` requests in 60 seconds must produce separate,
  correctly attributed decisions. Neither rehearsal may count the other health
  class, and the internal Docker liveness probe must bypass the public policy.
- [ ] For each public health policy, record an explicit `ENABLE` or `REJECT`
  decision after validating normal external-monitor frequency and failure
  behaviour. An `ENABLE` decision must prove its configured temporary ban,
  expiration, restart persistence and monitor recovery. A `REJECT` decision
  must name the compensating control, retained alert and explicit owner
  approval; silence or an unbounded public endpoint is not a decision.
- [ ] Expose only Caddy's minimized security-event log through a dedicated host
  directory readable by the host defence service and inaccessible to the web
  application.
- [ ] Install a persistent Fail2ban/nftables BOOKPILE policy with a persistent
  database and an independent enable/disable procedure.
- [ ] Run scanner detection in dry-run for at least 24 hours. A controlled 60
  scanner probes/minute fixture must be detected with the validated client IP
  and must not block traffic.
- [ ] Enable only the 10-minute high-confidence scanner ban; prove ban,
  expiration, service restart persistence and emergency unban from the IONOS
  console.
- [ ] Observe the `1,200 requests/minute/IP` edge-volume signal for seven days
  before deciding whether to enable its 10-minute ban. Record the explicit
  enable or reject decision here.
- [ ] Keep authentication and ambiguous API `401/404/422` signals alert-only
  until the Owner/Viewer and malformed-input baselines are complete.
- [ ] Prove equivalent rules before enabling public IPv6. Until then, record
  public IPv6 as disabled.

Evidence: configuration, distinct health fixtures and decisions, dry-run counts,
ban/unban/restart transcript and health-monitor continuity.

### D7 — Defensive regression harness

- [ ] Automate normal navigation, API burst, scanner paths, forged forwarding
  headers, fixed-window expiry, lease loss, slow/disconnected exports, multiple
  users per IP, multiple Owners per library, unauthorized IDs and secret
  redaction.
- [ ] Cover IPv4, IPv4-mapped IPv6 and native IPv6 parsing even while public
  IPv6 remains disabled.
- [ ] Run the harness before and after every enforcement-mode change and retain
  a machine-readable result tied to the deployment revision.

Evidence: CI job plus staging report with every scenario passing.

## 5. Owner/Viewer authorization audit

This entire section is a **production blocker**. Every test calls the API
directly; hiding a UI control is not evidence.

- [ ] A1: Create two synthetic Owners, two Viewers with different scopes and
  two unrelated libraries. Attempt cross-library reads and writes using valid
  foreign UUIDs for every resource family; require generic denial and no state
  change.
- [ ] A2: Audit catalogue CRUD, contributors, metadata options and private
  covers for Owner, catalogue-only Viewer and catalogue-and-map Viewer.
- [ ] A3: Audit personal readings, perspective selection, shared custody,
  statistics and loans; prove borrower/private notes never reach Viewers.
- [ ] A4: Audit bookcases, shelves, containers, map projections, physical
  positions and rearrangement preview/apply.
- [ ] A5: Audit library invitations, membership listing, map-scope changes,
  promotion, downgrade, removal and final-Owner protection, including stale and
  concurrent requests.
- [ ] A6: Audit Local ZIP preflight/consolidation and Server export/import,
  including cross-library job IDs, source identity mapping and failed-import
  residue.
- [ ] A7: Audit library and account deletion, 48-hour recovery, expired tokens,
  session revocation and final cleanup.
- [ ] A8: Audit profiles, discoverability, quota projections and every
  administrative field for overexposure.
- [ ] A9: Audit CSRF, session fixation/rotation, revoked sessions, concurrent
  membership changes and requests issued after access removal.
- [ ] A10: Convert every discovered defect into a regression test and publish a
  matrix containing endpoint, actor, expected result, actual result, revision
  and evidence. Zero unresolved authorization defects are permitted.

## 6. `SYSTEM_ADMIN` console

This entire section is a **production blocker**.

### A1 — Authorization and enrolment

- [ ] Add a platform-role model independent of library membership. No username,
  email address or library role may imply `SYSTEM_ADMIN`.
- [ ] Implement an offline host command that explicitly enrols or revokes an
  administrator and emits an immutable audit event.
- [ ] Prove that an administrator without membership receives the same denial
  as any other non-member for every private-library endpoint.

### A2 — Strong authentication

- [ ] Require a normal authenticated account plus a registered WebAuthn/FIDO2
  passkey or hardware security key before creating an admin session. SMS is not
  accepted as a factor.
- [ ] Provide one-time hashed recovery codes generated at enrolment and require
  offline custody; using a code revokes it and sends an operator alert.
- [ ] Use a separate HttpOnly, Secure, SameSite=Strict admin-session cookie with
  CSRF protection, 15-minute inactivity expiry and 30-minute absolute expiry.
- [ ] Require a WebAuthn step-up performed within the previous five minutes for
  every destructive action.
- [ ] For administrator enrolment/revocation, account suspension/reactivation
  and recovery-code regeneration, require an additional single-use confirmation
  sent to the separately configured operator email, expiring after ten minutes.
- [ ] Rate-limit admin login, WebAuthn assertions, recovery codes and email
  confirmations by validated IP and administrator identity; alert on every
  failed recovery-code or repeated step-up attempt.

### A3 — Immutable audit

- [ ] Store admin audit rows through a database role that can insert but cannot
  update or delete. Include operator, action, target opaque ID, reason,
  correlation ID, timestamp and result; never include secrets or private
  library content.
- [ ] Hash-chain audit rows and include them in encrypted off-site backups.
- [ ] Implement and schedule an integrity verifier; a broken chain or missing
  sequence raises a critical external alert.
- [ ] Prove application, worker and administrator roles cannot modify or delete
  an existing audit row.

### A4 — Allowed console capabilities

- [ ] Create and revoke account invitations.
- [ ] List the minimum account identity and state required for administration;
  suspend/reactivate an account and revoke its sessions with reason and step-up.
- [ ] Display storage entitlements, usage and aggregate capacity without
  exposing library names, book metadata or object keys.
- [ ] Display service/backup/email/deep-check health and D5 aggregates.
- [ ] Display filtered security cases and normalized events with time, event
  class, outcome, pseudonymous client correlation and deployment revision.
- [ ] Permit audited reveal of one retained client-IP field from one normalized
  security event only for an explicitly opened incident and after current
  WebAuthn step-up. The endpoint accepts the incident ID and event ID, not an IP
  search, and provides no bulk listing, export or access to the underlying raw
  request log.
- [ ] Provide no shell, Docker control, SQL console, secret viewer, raw-log
  browser, email body/token access, impersonation or private-library browsing.

### A5 — Console acceptance

- [ ] Test every route with ordinary user, Owner, Viewer, expired admin session,
  revoked administrator and valid administrator.
- [ ] Test CSRF, stolen normal session without WebAuthn, replayed assertion,
  expired email confirmation, consumed recovery code and direct object-ID
  manipulation.
- [ ] Complete keyboard, screen-reader, mobile and browser acceptance without
  weakening the authentication boundary.
- [ ] Rehearse enrolment, normal use, emergency revocation and audit verification
  in staging.

## 7. Staging and production infrastructure

### I1 — Staging host maintenance

- [x] Apply pending Ubuntu security updates in a documented maintenance window,
  perform the required reboot and verify SSH, firewall, Docker, Compose,
  systemd timers, API/web/worker health, external monitors and deep maintenance.
- [x] Record effective unattended-security-update and controlled-reboot policy.
- [x] Confirm only ports 22, 80 and 443 are public and record IPv4/IPv6 state
  after the reboot.

Evidence: the 2026-10-20 UTC maintenance window began from a clean checkout and
healthy revision `f306f30363358363d17d561268b548c2b908a8ff`. Verified backup
`bd4cabcb-edac-47a0-ab2c-c64fdbc7e595` contained all 436 artefacts, and the
pre-update deep check accounted for all 435 private objects. The host installed
35 package updates with zero removals or held packages, including Docker,
containerd, AppArmor, certificates and networking components, then rebooted at
19:14 UTC into Ubuntu 24.04.5 and kernel `6.8.0-147-generic`. Docker 29.9.1,
containerd 2.4.2 and Compose 5.6.0 recovered the database, API, email worker and
web service automatically. No package, boot-journal or systemd failure remained;
all six BOOKPILE timers were scheduled. Public live/readiness, Healthchecks and
the Sentry uptime monitor recovered. Sentry recorded one privacy-redacted email-
worker database connection error while Docker restarted at 19:10 UTC and no
later recurrence; it is accepted as a bounded maintenance interruption. The
post-reboot deep check again accounted for 435/435 objects with zero mismatch,
absence or orphan.

`unattended-upgrades` is enabled and active. APT refreshes package lists daily
and installs the configured Ubuntu base/security origins; `noble-updates`,
distribution upgrades and host reboots are not automatic. Required reboots are
performed manually in
an announced window only after a fresh verified backup, package simulation and
healthy pre-check, followed by the full I1 post-check recorded here.

The host retained IPv4 `31.70.142.191`, no global IPv6 address and no public
`AAAA` record. Host listeners and an independent workstation probe agreed that
TCP 22, 80 and 443 were reachable while 5432 and 8100 were closed/filtered; no
other public listener was present. Effective SSH policy remained public-key
authentication enabled with password and keyboard-interactive authentication
disabled.

### I2 — Reproducible production host

- [ ] Apply the checked-in idempotent host bootstrap to the production VPS from
  a supported clean Ubuntu 24.04 image; no manual undocumented package or
  configuration step is permitted.
- [ ] Compare package sources, Docker/Compose versions, users, permissions,
  firewall, networks, systemd units, log policy, directories and kernel/security
  update state with staging. Store a machine-readable difference report and
  resolve every unexplained difference.
- [ ] Provision production-only DNS/TLS, PostgreSQL, active-object bucket,
  backup bucket, SMTP credential, Sentry project, Healthchecks checks and
  application secrets. Prove staging credentials cannot reach them.
- [ ] Prove Local, CI and test configuration cannot resolve credentials or
  connect to production data services.

### I3 — Immutable promotion pipeline

- [ ] Make CI build API, web and backup images once per approved commit, scan
  them, generate an SBOM and publish immutable digest-addressed images to the
  selected private registry.
- [ ] Deploy those exact digests to staging and record the accepted release
  manifest. Production promotion consumes that manifest and never rebuilds.
- [ ] Implement production preflight, verified backup, explicit forward
  migration, service rollout, health/deep checks and automatic stop on failure.
- [ ] Implement configuration-first application rollback to the previous
  manifest. Database restoration remains a separately authorized disaster-
  recovery action; schema downgrade is never automatic.
- [ ] Rehearse a no-schema release, an additive-schema release, failed health
  rollout and application rollback in both staging and disposable production.

### I4 — Data separation and portability

- [ ] Prove deployment changes code/images/configuration only: create production
  data, promote a later staging-approved release and verify every production
  account, library, book, reading and object checksum remains unchanged.
- [ ] Export one entirely synthetic library from staging and import it into a
  distinct synthetic production account using the normal portable-ZIP flow;
  verify counts, checksums, identity mapping and isolation.
- [ ] Before opening production, destroy and recreate the production database
  and object namespace after acceptance testing, apply migrations to an empty
  database and prove zero accounts, invitations, libraries, books, sessions,
  jobs and private objects. Staging synthetic data is not copied or deleted.

## 8. Capacity and reliability evidence

This section is a **production blocker**. The private-beta acceptance envelope
is 50 invited accounts, 10 concurrent active users, 25,000 books and 5,000
private images.

- [ ] Generate a reproducible synthetic dataset matching the envelope without
  using personal staging data.
- [ ] Measure API latency, PostgreSQL connections/locks, worker queue age, CPU,
  peak resident memory, disk/inodes and object traffic during login, catalogue,
  map, cover, import and export workloads.
- [ ] Pass the envelope with zero unexpected `5xx`, zero integrity failures,
  no pool exhaustion, host memory below 80%, root disk below 70%, p95 ordinary
  reads below one second and p95 ordinary mutations below two seconds.
- [ ] Measure backup and restore at the envelope; retain RPO at or below 24
  hours and RTO at or below four hours.
- [ ] Configure alert thresholds below measured failure points and prove warning,
  critical and recovery delivery.
- [ ] Record monthly provider cost and storage/traffic headroom at the envelope.

## 9. Security maintenance and dependencies

- [ ] Review every open Dependabot PR against release notes, lockfile changes,
  compatibility and CI; merge accepted updates through normal review.
- [ ] Reach zero applicable critical or high GitHub security alerts. Record an
  owner, rationale and review date for every accepted exception; unresolved
  exploitable high/critical findings block production.
- [ ] Generate and retain dependency and container vulnerability reports for
  the exact production release manifest.
- [ ] Document monthly dependency review and emergency security-patch procedure.

## 10. Policies, legal text and user documentation

This section is a **production blocker**.

- [ ] Publish the 100 MB beta entitlement, what counts toward it, behaviour at
  the hard limit and the operator-controlled mechanism for future tiers.
- [ ] Publish backup scope, 29-day operational retention, recovery limitations
  and the distinction between operational backup and user portable export.
- [ ] Publish export/portability instructions and test them against the released
  interface.
- [ ] Publish account/library deletion, 48-hour recovery and permanent-cleanup
  behaviour. Name exactly which authenticated role may cancel a pending shared-
  library deletion and prove the published rule matches direct API tests.
- [ ] Publish privacy information covering controller/contact, purposes, legal
  bases, data categories, processors/subprocessors, EU locations, retention,
  security-event/IP use, international transfers if any and data-subject rights.
- [ ] Publish terms of use, acceptable-use/abuse rules, support and security
  contact, copyright/licensing and service limitations.
- [ ] Implement and record every required consent or acknowledgement with
  version, timestamp and withdrawal/update handling; do not use bundled consent
  where it is not legally appropriate.
- [ ] Review all public text against the implemented behaviour and provider
  contracts; record the review date and reviewer.

## 11. Final acceptance

- [ ] Run invitation, registration, verification, login/logout, password reset,
  deletion recovery and session-revocation journeys.
- [ ] Record and verify the effective invitation, verification, password-reset,
  normal-session, remembered-session, deletion-recovery and admin-confirmation
  expiry periods against configuration, UI/email copy and boundary-time tests.
- [ ] Run a ten-language matrix covering preference change, reload, fresh
  browser, second device, auth links, email subjects/bodies, dates, numbers,
  accessibility names and mobile layout. The already accepted implementation
  remains closed; this is release-candidate regression evidence.
- [ ] Run import, export, restore, Owner/Viewer and concurrent-user journeys.
- [ ] Pass current Chrome, Firefox and Safari on desktop and mobile/tablet where
  available; record exact versions and exceptions.
- [ ] Pass mobile installation acceptance: install/add BOOKPILE to the home
  screen from current Android Chrome and iOS Safari, launch it from the icon,
  authenticate, retain the selected language, navigate catalogue and map, then
  deploy a newer compatible build and prove the installed entry is not stranded
  on stale assets. Document that the beta requires connectivity and makes no
  offline-availability promise.
- [ ] Pass keyboard-only use, visible focus, semantic labels, contrast and a
  basic screen-reader journey for authentication, catalogue, map and admin.
- [ ] Rehearse final production deployment, application rollback, total-host
  recovery and provider export with synthetic data.
- [ ] Confirm external monitoring, email reputation and bounce/failure visibility.

## 12. Phase 9G and private-beta opening

- [ ] Reconcile every active runbook and ADR with this plan; no active document
  may claim a conflicting quota, provider, domain, status or release gate.
- [ ] Verify every task in sections 4 through 12 is complete. No exception may
  be inferred from the absence of a local **production blocker** label.
- [ ] Record the exact production release manifest, SBOM, migration revision,
  provider inventory, costs, unresolved low-risk limitations and rollback
  references.
- [ ] Confirm production contains no synthetic users, invitations, libraries,
  books, sessions, jobs or objects and that the first administrator is enrolled
  through the approved offline procedure.
- [ ] Record an explicit signed go/no-go decision. Only `GO` authorizes creation
  of the first real invitation.

## 13. Post-beta work, not release blocking

Every item here is intentionally non-blocking for the invitation beta. An
evaluation task closes only with a committed decision record that says
`ACCEPTED` or `REJECTED`, names the evidence and, when accepted, creates the
implementation task in this section.

### P1 — Local maintenance and parity

- [ ] Add Local interface localization in an isolated maintenance branch while
  preserving the English-only `v1.0.0` artifact; pass clean-install, backup,
  restore and desktop/mobile language acceptance before releasing it.
- [ ] Backport the accepted Server physical-geometry behaviour to Local using a
  verified ZIP, isolated worktree, additive rehearsed SQLite migration and the
  active geometry specification; never test against the populated Local data.
- [ ] Publish Local manual-recovery and safe-backup-storage instructions and
  rehearse them against an isolated installation.
- [ ] Evaluate realistic supported-PILE tilt with two contact points, rotated
  rendering, transformed hitboxes and collision rules; close with an accepted
  or rejected geometry decision and prototype evidence.

### P2 — Capture and bibliographic enrichment

- [ ] Implement multi-source ISBN enrichment for Local and Server: normalize
  candidates from every configured provider, preserve provenance, display
  conflicts, merge genuine contributor roles without duplication and require
  explicit field-level review before saving.
- [ ] Evaluate continuous live barcode scanning over a trusted HTTPS/installable
  capture path. The prototype must stop camera streams, debounce repeated codes
  and retain typed ISBN/photo scanning as fallbacks; record `ACCEPTED` or
  `REJECTED` with mobile evidence.
- [ ] Evaluate advanced OCR only after measuring the current OCR workflow.
  Record accuracy, latency, supported devices and maintenance cost, then record
  `ACCEPTED` or `REJECTED`; no implementation follows without acceptance.
- [ ] Audit Local and Server parity for edition language versus original work
  language and ordered contributor roles. Implement every missing schema,
  details/edit/search/import/export and ISBN-review path, with lossless migration
  evidence in both editions.

### P3 — Rich metadata and discovery

- [ ] Add structured subjects with versioned import/export and searchable,
  editable Local/Server projections.
- [ ] Replace interim free-text genre storage with structured genres through a
  lossless migration that preserves every existing value and exposes unresolved
  values for review.
- [ ] Add free-form tags with normalization, search, import/export and privacy-
  safe Server ownership semantics.
- [ ] Add an optional personal rating owned by the reader, never shared as
  library metadata; cover Local/Server migration, import/export and privacy.
- [ ] After ratings exist, add personal-rating map colouring with an accessible
  legend and missing-data state.
- [ ] Implement near-match suggestions only after committing a normalization
  strategy for free-text language and genre values; prove that suggestions do
  not silently rewrite metadata.
- [ ] Evaluate optional physical-move history with retention, storage and
  privacy costs; record `ACCEPTED` or `REJECTED` and, if accepted, add a separate
  implementation task.

### P4 — Later product policy

- [ ] Observe beta storage usage before defining paid plans. Record an accepted
  entitlement/tier decision; different byte limits and plan codes must not
  change library ownership semantics.
- [ ] Evaluate username-discovery opt-out with search-abuse and privacy evidence;
  record `ACCEPTED` or `REJECTED` before changing discovery.
- [ ] Consider friendship, blocking and public catalogues only after an accepted
  moderation, reporting and privacy design.
- [ ] Consider German, Japanese, Dutch, Greek, Arabic and Korean; each language
  requires the full launch-language contract and Arabic requires an RTL audit.
- [ ] Clean old merged branches while preserving branches with unique commits,
  open PRs and `release/local-v1`.

## 14. Execution order

This ordering does not duplicate task status; completion is recorded only in
the sections above.

1. **Evidence and edge:** complete D3-L, then D5, D6 and the full D7 harness;
   D4-G, D4-M, D4-S and D4-O are accepted and active in staging.
2. **Authorization:** execute Owner/Viewer A1-A10 while defensive edge evidence
   accumulates; authorization defects pre-empt all feature work.
3. **Administration:** implement the `SYSTEM_ADMIN` domain, strong
   authentication, immutable audit and restricted console.
4. **Production platform:** reproduce the production host, implement immutable
   image promotion and prove environment/data separation.
5. **Readiness:** complete capacity, dependencies, policies/legal text and final
   cross-browser/accessibility acceptance.
7. **Opening:** complete Phase 9G and record explicit `GO` or `NO-GO`.

## 15. Legacy-roadmap disposition

The unchecked items from `old/TODO-legacy-2026-10-18.md` have the following
complete disposition. This table is an audit trail, not another task list.

| Legacy item | Authoritative disposition |
| --- | --- |
| Multilingual Local and Server interfaces | Server implementation accepted in section 3; release regression in section 11; Local work in P1. |
| Server-to-Local visual/geometry parity | Active specification plus P1. |
| Manual recovery and safe backup documentation | P1. |
| Multi-source ISBN enrichment | P2. |
| Continuous barcode scanning | P2 evaluation. |
| Advanced OCR | P2 evaluation. |
| Original/edition language and contributor-role parity | P2 audit and implementation. |
| Server canonical geometry | Completed baseline; Local backport in P1. |
| Supported PILE tilt | P1 evaluation. |
| Subjects, structured genres, tags and ratings | P3. |
| Rating map colouring | P3, ordered after ratings. |
| Near-match normalization/suggestions | P3. |
| Physical-move history | P3 evaluation. |
| Remaining multi-user decisions | Beta decisions are fixed in section 2 or covered by sections 4-12; discovery and monetization remain in P4. Portable exports are streamed and are not retained as user snapshots during the beta. |
| Viewer-safe authorization for every domain | Section 5. |
| Friendship, blocking and public catalogues | P4. |
| Phase 9 and 9G | Sections 4-12. |
| Server internationalization | Accepted baseline plus section 11 regression. |
| Production providers/adapters | Section 7. |
| Authorization checks | Section 5. |
| Platform administration | Section 6 and ADR 0017. |
| Defensive security | Section 4. |
| Storage, backup, deletion and export policies | Section 10. |
| Deployment and rollback | Section 7. |
| Responsive/accessibility/browser and mobile-installation acceptance | Section 11. |
| Terms, privacy and consent | Section 10. |
