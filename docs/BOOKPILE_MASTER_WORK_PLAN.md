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
- Every completion change must name a commit or deployed revision and the
  retained evidence. A statement such as "works" without evidence is not a
  closure.
- A newly discovered release-blocking task must be added here before work on it
  starts. It must not be tracked only in a PR, ADR, chat or external checklist.
- Production may open only when every item explicitly labelled **production
  blocker** is complete and the final go/no-go is recorded.

## 2. Fixed product and operational decisions

- [x] The invitation-only beta has ten launch languages: English, Galician,
  Spanish, Portuguese, Catalan/Valencian, Italian, Basque, French, Aranese
  Occitan and Simplified Chinese.
- [x] The beta storage entitlement is exactly `100_000_000` bytes per account
  (decimal 100 MB). Entitlements remain rows in
  `account_storage_entitlements`, so a future operator may assign different
  limits or plan codes without changing catalogue ownership semantics.
- [x] Staging and production contain independent databases, object buckets,
  backup repositories, SMTP credentials, monitoring projects, secrets and
  cookies. No database, account, library, book or object is copied from staging
  as part of deployment.
- [x] A portable Server ZIP may be exported by an authorized Owner in staging
  and imported by an authorized Owner in production through the normal guarded
  import flow. This is user-directed data portability, not environment cloning.
- [x] Production receives the same immutable application image digests already
  accepted in staging. Environment configuration and secrets differ; code and
  image contents do not.
- [x] A web `SYSTEM_ADMIN` console is a production blocker. It is a separate
  authorization domain and never grants library membership or implicit access
  to private catalogues, maps, covers, readings, loans, exports or email bodies.
- [x] Raw host, Docker, Caddy and application logs remain host-side. The admin
  console exposes normalized, minimized security and operational events, not a
  shell, arbitrary log reader, filesystem browser or secret viewer.
- [x] The general API IP limit does not require representative public traffic
  in staging. Its rollout gate is deterministic: automated concurrency tests,
  a bounded observe-mode rehearsal, enforce-mode rehearsal, normal functional
  use and a deep operational check.

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
- [x] The general `/api/*` IP ceiling is deployed in observe mode at revision
  `b3700d2882fcde5c08a0ea69e585529880eaec06`. A 650-request/10-second rehearsal
  produced 650 normal `404` responses, one HMAC-keyed bucket with count 650 and
  one revision-labelled `rate_limit_observed`; the deep check remained healthy.

## 4. Defensive security programme

Every item in this section is a **production blocker** unless explicitly marked
otherwise.

### D3-L — Log retention and safe investigation

- [ ] Define one retention table covering Caddy edge events, application
  request events, security events, journald, Sentry and immutable admin audit.
  The table records fields retained, purpose, exact duration, deletion method,
  access role and legal-policy reference.
- [ ] Configure strict time-based expiry for the active Caddy log. Prove with a
  disposable dated fixture that records older than the configured duration are
  absent after rotation while newer records remain readable.
- [ ] Bound journald by both time and disk use; capture `journalctl --disk-usage`
  and effective configuration before and after a controlled service restart.
- [ ] Verify that no retained event contains cookies, authorization headers,
  CSRF values, reset/invitation tokens, request bodies, email content, object
  keys or catalogue data.
- [ ] Document and test the host-only incident procedure for authorized access
  to raw IP evidence. Every access must record operator, reason, incident,
  timestamp and result in the immutable admin audit.

Evidence: committed retention table and runbook; staging rotation transcript;
redaction tests; one audited raw-evidence access rehearsal.

### D4-G — General API IP ceiling

- [ ] Change `BOOKPILE_SERVER_GENERAL_API_LIMIT_MODE` from `observe` to
  `enforce` in staging and recreate only the API.
- [ ] In a fresh fixed window, run a bounded 650-request rehearsal and prove
  that requests through the threshold retain their normal response, excess
  requests return generic `429` with `Retry-After`, exactly one
  `rate_limit_blocked` event is emitted and no raw IP is stored in the bucket or
  event.
- [ ] Complete normal login, catalogue, cover and map use after the rehearsal;
  prove `/health/live`, `/health/ready`, frontend and static assets are not
  counted; run the deep operational check.
- [ ] Exercise two API workers concurrently and prove that their combined
  decisions cannot exceed the configured shared threshold.

Evidence: command output, event/bucket status, response headers, revision and
deep-check result.

### D4-M — Authenticated and library mutation ceilings

- [ ] Implement a PostgreSQL-backed `240/15 minutes` ceiling per authenticated
  user for state-changing API operations, independently configurable as
  `off/observe/enforce`.
- [ ] Implement a PostgreSQL-backed `600/15 minutes` ceiling per authorized
  library for state-changing operations. An unauthorized or nonexistent
  library identifier must not consume a library bucket.
- [ ] Prove atomic decisions across two workers, fixed-window reset,
  `Retry-After`, generic `429`, fail-closed generic `503`, HMAC key privacy and
  independent rollback switches.
- [ ] Prove that two users behind one IP and two co-Owners in one library receive
  the intended independent user, library and IP decisions.

Evidence: migration if required, tests, staging observe/enforce rehearsal and
normal multi-owner functional test.

### D4-S — Specific operation ceilings

- [ ] Add the authorized-library bibliographic lookup ceiling of `360/hour`
  alongside the existing client-IP and user controls.
- [ ] Add the authorized-library cover-upload ceiling of `120/hour` alongside
  the existing `30/hour/user` control.
- [ ] Add rearrangement preview/apply observation at `120/minute/user` and
  `240/minute/library`; enforce only after automated normal interaction remains
  below 25% of both thresholds.
- [ ] Prove that rejected lookups, uploads and rearrangements leave no database
  or object residue and return only generic policy responses.

Evidence: focused tests, staging status/events, one accepted normal workflow for
each operation and one bounded blocking rehearsal.

### D4-O — Abandoned private-object recovery

- [ ] Implement a dry-run command that lists only private objects absent from
  committed metadata, older than a configured grace period and not protected
  by an active import/export lease or in-flight job.
- [ ] Make deletion opt-in, bounded per run, exact-key based and auditable. A
  database or lease decision failure must stop deletion.
- [ ] Run dry-run against staging, inject one disposable orphan, prove detection
  without touching 435 expected objects, delete only the disposable orphan and
  pass deep reconciliation.
- [ ] Schedule the accepted bounded cleanup and alert on failure or a non-zero
  backlog; document the independent disable switch.

Evidence: tests for race/failure/grace-period cases and the staging injection,
cleanup and deep-check transcript.

### D5 — Aggregate detection and alerting

- [ ] Produce aggregate metrics for `429`, `503`, lease conflicts, scanner
  probes, temporary bans, repeated validation failures and `5xx`, labelled by
  policy/scope/revision but never by raw identity or request content.
- [ ] Define exact warning and critical thresholds, alert destination, grouping
  window, recovery notification and owner for every metric.
- [ ] Trigger one disposable warning and one disposable critical alert in
  staging; prove delivery, deduplication and recovery without exposing private
  data.
- [ ] Expose the same sanitized aggregates in the `SYSTEM_ADMIN` console.

Evidence: metric catalogue, alert configuration and alert/recovery receipts.

### D6 — Edge defence before Python

- [ ] Make Caddy emit mutually exclusive fixed labels `health_class=live`,
  `health_class=ready` and `health_class=other`, deleting original URI and query
  data; prove one fixture cannot match two classes.
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

Evidence: configuration, fixtures, dry-run counts, ban/unban/restart transcript
and health-monitor continuity.

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
- [ ] Permit audited access to a retained raw client IP only for an explicitly
  opened security incident, after current WebAuthn step-up. Do not expose raw
  request logs or arbitrary searches.
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

- [ ] Apply pending Ubuntu security updates in a documented maintenance window,
  perform the required reboot and verify SSH, firewall, Docker, Compose,
  systemd timers, API/web/worker health, external monitors and deep maintenance.
- [ ] Record effective unattended-security-update and controlled-reboot policy.
- [ ] Confirm only ports 22, 80 and 443 are public and record IPv4/IPv6 state
  after the reboot.

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
  behaviour.
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
- [ ] Run a ten-language matrix covering preference change, reload, fresh
  browser, second device, auth links, email subjects/bodies, dates, numbers,
  accessibility names and mobile layout. The already accepted implementation
  remains closed; this is release-candidate regression evidence.
- [ ] Run import, export, restore, Owner/Viewer and concurrent-user journeys.
- [ ] Pass current Chrome, Firefox and Safari on desktop and mobile/tablet where
  available; record exact versions and exceptions.
- [ ] Pass keyboard-only use, visible focus, semantic labels, contrast and a
  basic screen-reader journey for authentication, catalogue, map and admin.
- [ ] Rehearse final production deployment, application rollback, total-host
  recovery and provider export with synthetic data.
- [ ] Confirm external monitoring, email reputation and bounce/failure visibility.

## 12. Phase 9G and private-beta opening

- [ ] Reconcile every active runbook and ADR with this plan; no active document
  may claim a conflicting quota, provider, domain, status or release gate.
- [ ] Verify every **production blocker** in this document is complete.
- [ ] Record the exact production release manifest, SBOM, migration revision,
  provider inventory, costs, unresolved low-risk limitations and rollback
  references.
- [ ] Confirm production contains no synthetic users, invitations, libraries,
  books, sessions, jobs or objects and that the first administrator is enrolled
  through the approved offline procedure.
- [ ] Record an explicit signed go/no-go decision. Only `GO` authorizes creation
  of the first real invitation.

## 13. Post-beta work, not release blocking

- [ ] Observe usage before defining paid plans; the entitlement model may assign
  different byte limits and plan codes without changing library ownership.
- [ ] Consider friendship, blocking and public catalogues only after a separate
  moderation/privacy design.
- [ ] Backport selected Server geometry and internationalization work to a
  future Local release through its isolated maintenance process.
- [ ] Consider German, Japanese, Dutch, Greek, Arabic and Korean; Arabic requires
  a complete RTL audit.
- [ ] Clean old merged branches while preserving branches with unique commits,
  open PRs and `release/local-v1`.

## 14. Execution order

This ordering does not duplicate task status; completion is recorded only in
the sections above.

1. **Immediate:** complete D4-G enforce-mode acceptance and perform I1 staging
   security updates/reboot in a separately announced maintenance window.
2. **Application limits:** implement D4-M, D4-S and D4-O in small reviewed PRs.
3. **Evidence and edge:** complete D3-L, then D5, D6 and the full D7 harness.
4. **Authorization:** execute Owner/Viewer A1-A10 while defensive edge evidence
   accumulates; authorization defects pre-empt all feature work.
5. **Administration:** implement the `SYSTEM_ADMIN` domain, strong
   authentication, immutable audit and restricted console.
6. **Production platform:** reproduce the production host, implement immutable
   image promotion and prove environment/data separation.
7. **Readiness:** complete capacity, dependencies, policies/legal text and final
   cross-browser/accessibility acceptance.
8. **Opening:** complete Phase 9G and record explicit `GO` or `NO-GO`.
