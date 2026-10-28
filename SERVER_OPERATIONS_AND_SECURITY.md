# BOOKPILE Server operations and security boundary

## Automated jobs

The production Compose `operations` profile exposes two non-public commands:

- `bookpile-maintenance run` finalizes elapsed library/account deletion windows,
  expires import staging, and prunes old rate buckets, sessions, action tokens,
  invitations, delivered outbox payloads and security events.
- `bookpile-maintenance check [--deep]` returns aggregate JSON and a non-zero
  status for failed/overdue email, overdue deletion cleanup or private-object
  inventory differences. Deep mode reads and hashes all objects and therefore
  runs daily, not every five minutes.

Retention is deliberate: rate buckets 2 days; expired or revoked sessions 7
days; delivered/cancelled email 7 days; failed email and action/invitation
material 30 days; security events 180 days. Library audit history is not
globally pruned because it belongs to each active library and requires a
separate product retention decision.

### Abandoned private-object recovery

Private-object cleanup is independent from normal deletion cleanup and defaults
to `off`. Its three modes are:

- `off`: scheduled maintenance does not inventory or delete abandoned objects;
- `observe`: hourly maintenance reports eligible candidates but never deletes;
- `enforce`: hourly maintenance deletes at most the configured batch limit.

An object is eligible only when no cover/profile metadata references its exact
key, its provider `LastModified` is at least the configured grace age, and no
active import/export lease or `READY`/`IMPORTING` import job exists. Unknown
ages fail closed. Apply mode repeats the database, active-work, age, size,
checksum and modification-time checks immediately before each exact-key delete,
then verifies absence. PostgreSQL holds the metadata, lease and import-job
tables against concurrent writes across the final checks and external delete.
A failed database, lease or storage decision stops the run. Authorization and
completion events retain only a keyed HMAC, byte count and deployment revision;
commands never print raw object keys.

The defaults are a 24-hour grace and at most 25 deletions per run. Inspect a
read-only plan regardless of the scheduled mode:

```bash
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml --profile operations run --rm maintenance \
  bookpile-private-objects recover-orphans
```

Manual apply requires both `BOOKPILE_SERVER_PRIVATE_OBJECT_ORPHAN_CLEANUP_MODE`
set to `enforce` and an explicit confirmation:

```bash
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml --profile operations run --rm maintenance \
  bookpile-private-objects recover-orphans --apply \
  --confirm DELETE-ABANDONED-PRIVATE-OBJECTS
```

For the controlled staging acceptance only, create one 32-byte disposable
orphan with an audited, staging-restricted command. It returns only the HMAC
needed to correlate the later dry-run and deletion. Wait until the configured
grace has elapsed before expecting it to become eligible:

```bash
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml --profile operations run --rm maintenance \
  bookpile-private-objects inject-orphan-rehearsal \
  --confirm STAGING-ORPHAN-REHEARSAL
```

Rollback is immediate: set the independent mode to `off`; subsequent one-shot
maintenance containers will not run orphan recovery. The daily deep check
remains the non-zero-backlog alert and must return exact inventory after an
accepted cleanup. Never reduce the production grace to accelerate a rehearsal.

### Defensive HTTP observation

Caddy 2.11.7 writes a minimized access log to `/data/access.log` in its private
persistent volume. It records client address, method, status, duration and
size, but deletes request and response headers and the complete URI including
its query string. Browser requests retain their original path; API and health
paths are reduced to `/api/*` and `/health*` so edge-generated 413/502 responses
remain visible without retaining private identifiers. Known scanner probes are
labelled `scanner_probe`. The active file rolls every day at 00:00 UTC or at
10 MiB, whichever occurs first. Caddy keeps at most 14 rolled files and removes
rolls older than 14 days, so low traffic cannot keep the active file alive
beyond the temporal boundary. Before the first 2.11 deployment, the staging
deployment runs the bounded `migrate-caddy-access-log-rolls` command against
the existing `caddy-data` volume. It renames only exact Caddy 2.10 Lumberjack
rolls from `access-<timestamp>.log[.gz]` to the reason-suffixed form parsed by
2.11 Timberjack, refuses to overwrite a target and refuses more than 100
matches. The command is idempotent; once renamed, Timberjack applies the same
age and count expiry instead of leaving legacy rolls outside retention.

API request events contain route templates rather than raw identifiers, a
keyed client pseudonym rather than the raw IP, and no bodies, queries, cookies
or authorization material. Core service stdout/stderr uses Docker's `journald`
driver. The committed host policy limits the persistent journal to 14 days,
512 MiB and at least 1 GiB free space. Access to either source requires host
authority; do not export these logs into tickets or routine chat. The complete
field, purpose, deletion and access contract is
`docs/LOG_RETENTION_AND_INVESTIGATION_POLICY.md`.

PostgreSQL writes only terse operational errors: failing SQL statements,
parameter values and `DETAIL`/`HINT`/`QUERY`/`CONTEXT` fields are disabled so a
constraint failure cannot place an email address or catalogue value in the
host journal. Do not relax those settings for routine diagnosis.

Install the journald policy before recreating services on a host:

```bash
sudo install -o root -g root -m 0644 \
  server/deploy/journald/60-bookpile-retention.conf.example \
  /etc/systemd/journald.conf.d/60-bookpile-retention.conf
sudo systemd-analyze cat-config systemd/journald.conf
sudo journalctl --disk-usage
sudo systemctl restart systemd-journald.service
sudo journalctl --rotate
sudo journalctl --vacuum-time=14d --vacuum-size=512M
sudo journalctl --disk-usage
```

Record the effective `Storage`, `SystemMaxUse`, `SystemKeepFree`,
`SystemMaxFileSize`, `MaxRetentionSec` and `MaxFileSec` values before and after
the controlled restart. A journal restart does not restart BOOKPILE containers,
but public health and `bookpile-maintenance check --deep` must pass afterwards.

After recreating the long-lived containers, prove the minimized application
request logger is connected to the host journal rather than merely configured
in Python. Generate one controlled route without private identifiers and query
only its normalized event class:

```bash
curl --fail --silent --show-error \
  https://staging.bookpile.gal/health/live >/dev/null
sudo journalctl --since "2 minutes ago" \
  -t 'bookpile/bookpile-production-api-1' -o cat \
  | grep -F '"event":"http_request"' \
  | tail -n 5
```

At least one row must contain the route template `/health/live`, a keyed
`client_key` and the deployed revision. It must not contain a raw address,
query, header or body. An empty result fails D3-L acceptance even when the
Python redaction tests pass.

After deploying the accepted Caddy image, exercise its real temporal writer in
an isolated, networkless disposable container:

```bash
BOOKPILE_CADDY_IMAGE="$(docker inspect \
  --format '{{.Config.Image}}' bookpile-production-web-1)" \
  sh server/scripts/rehearse-caddy-log-retention.sh
```

The command must return `caddy_time_rotation`, `legacy_roll_migration`,
`old_fixture_absent` and `new_fixture_readable` as `true`. The fixture includes
expired and current files in both the old Lumberjack and new Timberjack naming
formats. Its container explicitly uses the host operator's UID/GID so the
non-root deployed image can read and write the mode-0700 temporary directory.
It never opens a host port or touches the live access-log volume. Retain the
JSON result and deployed image digest with the D3-L staging evidence.

Exercise PostgreSQL's retained-error boundary in a second disposable container:

```bash
BOOKPILE_POSTGRES_IMAGE="$(docker inspect \
  --format '{{.Config.Image}}' bookpile-production-db-1)" \
  sh server/scripts/rehearse-postgresql-log-redaction.sh
```

It must retain the synthetic constraint error while returning
`private_value_absent` and `statement_absent` as `true`. The fixture uses its
own temporary database container and never connects to BOOKPILE data.

### Staging D3-L acceptance — 2026-10-26

Revision `a40add206581940bf3b386d4e2ae7a41a040873a` installed the effective
journald policy at 14 days, 512 MiB, 1 GiB free, 64 MiB per file and one day
per file. Controlled restart, rotation and vacuum reduced journal use from
575.7 MiB to 188.0 MiB; database, API, email worker and web all reported the
`journald` logging driver. The deployed-image Caddy rehearsal returned
`caddy_time_rotation`, `legacy_roll_migration`, `new_fixture_readable` and
`old_fixture_absent` as true. The PostgreSQL rehearsal returned
`postgres_error_retained`, `private_value_absent` and `statement_absent` as
true. Deep reconciliation remained healthy at 440 expected and 440 stored
private objects.

The first live journal query correctly failed acceptance because no
`http_request` row was emitted: the minimized logger had no process output
handler. Revision `af10471343da73687cf7e4fd9b1139cd634f93d8` corrected that
gap and a fresh public probe produced real `/health/live` and `/health/ready`
events with route templates, status, duration, revision and keyed 16-hex client
pseudonyms. The retained rows contained no raw address, query, header, body or
private catalogue value. Together with the exhaustive synthetic-secret tests,
this accepts Caddy expiry, bounded journald and retained-event redaction. It
does not accept raw-evidence access or the future console-mediated IP reveal;
that separate gate remains open pending immutable admin audit and A3/A4.

Inspect recent scanner evidence on the host without copying the full file:

```bash
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml \
  exec -T web sh -c 'grep -F scanner_probe /data/access.log | tail -n 20'
```

Example systemd units and timers live in `server/deploy/systemd`: backup daily,
maintenance hourly, lightweight checks every 15 minutes, defensive metric
collection every 15 minutes, backup freshness every 15 minutes and full
private-object reconciliation daily.

Install copies without the `.example` suffix, correct `WorkingDirectory`, run
`systemctl daemon-reload`, enable the timers, and connect unit failure to the
chosen paging route. Monitoring evaluates exit status; a verified backup older
than 25 hours is unhealthy.

### External backup dead-man switch (staging)

The external check `BOOKPILE staging - backup diario` expects the daily
02:17 UTC backup with one hour of grace and sends email to the independent
operator mailbox. The Healthchecks ping URL is a bearer secret: keep it only
in `/etc/bookpile/healthchecks-backup.curl`, root-owned, mode `600`; never put
it in a unit, command argument, Git, logs or chat. The reproducible templates
are `server/deploy/healthchecks-backup.curl.example` and
`server/deploy/systemd/bookpile-backup-healthchecks.conf.example`.

Install the curl config and the latter as a systemd drop-in named
`/etc/systemd/system/bookpile-backup.service.d/10-healthchecks.conf`, then
`systemctl daemon-reload` and `systemd-analyze verify bookpile-backup.service`.
The drop-in sends an empty HTTPS GET only after a successful backup. Its
`ExecStartPost=-` deliberately ignores a ping/network failure so a verified
snapshot is not reclassified as failed. A missing ping, failed job, stopped
timer or lost host causes Healthchecks to alert after grace. Test first with
the protected curl configuration, then with a real oneshot; prove an external
email notification using a disposable check or Healthchecks' notification test
without corrupting a real backup. This is not website-uptime monitoring.

### External hourly-maintenance dead-man switch (staging)

The external check `BOOKPILE staging - mantenimiento horario` follows the
staging `*-*-* *:11:00` systemd timer in UTC. Configure it as an hourly cron
check with 30 minutes of grace. A run taking longer than that is itself
operationally abnormal even though systemd retains a one-hour hard timeout.
Keep its distinct bearer URL only in
`/etc/bookpile/healthchecks-maintenance.curl`, root-owned and mode `600`.
Reproducible examples are
`server/deploy/healthchecks-maintenance.curl.example` and
`server/deploy/systemd/bookpile-maintenance-healthchecks.conf.example`.
Install the latter as
`/etc/systemd/system/bookpile-maintenance.service.d/10-healthchecks.conf`.

The drop-in sends success only after the complete maintenance command exits
zero. A cleanup coordination failure, object-provider failure, stopped timer
or lost host therefore produces no ping and becomes externally visible before
the next hourly run can mask it. `ExecStartPost=-` keeps a Healthchecks outage
from changing an otherwise successful maintenance result. Validate the unit
with `systemd-analyze verify`, exercise a successful oneshot, and prove the
operator email route with Healthchecks' notification test; never manufacture
a failure against live private objects.

### External lightweight-operations dead-man switch (staging)

The external check `BOOKPILE staging - operaciones` follows the staging
`*:0/15` systemd timer in UTC with ten minutes of grace and uses the same
verified operator-email integration. Keep its distinct bearer URL only in
`/etc/bookpile/healthchecks-operations.curl`, root-owned and mode `600`.
Reproducible examples are
`server/deploy/healthchecks-operations.curl.example` and
`server/deploy/systemd/bookpile-operations-check-healthchecks.conf.example`.
Install the latter as
`/etc/systemd/system/bookpile-operations-check.service.d/10-healthchecks.conf`.

The drop-in sends success only after `bookpile-maintenance check` exits zero.
An unhealthy database, overdue deletion cleanup, overdue/failed email, stopped
timer or lost host therefore produces no ping and becomes externally visible
after the grace period. As with backup monitoring, `ExecStartPost=-` prevents
a Healthchecks outage from changing BOOKPILE's own check result. Validate every
manual edit with `systemd-analyze verify` before relying on the monitor.
Deletion cleanup is considered overdue only 75 minutes after its recovery
window closes. This gives the hourly maintenance job one complete interval plus
scheduling headroom; a pending deletion inside that grace period is expected,
not an operational failure.

The daily deep reconciliation has a separate check named
`BOOKPILE staging - reconciliación privada diaria`. It follows
`*-*-* 04:05:00` UTC with two hours and fifteen minutes of grace, allowing the
two-hour unit timeout as the private inventory grows. Its protected config is
`/etc/bookpile/healthchecks-deep-check.curl`; install
`bookpile-deep-check-healthchecks.conf.example` as the service's
`10-healthchecks.conf` drop-in. It reports success only after database/outbox/
deletion checks and the complete private-object count/hash reconciliation pass.

### Host capacity thresholds

Install `server/deploy/check-host-capacity.sh` as
`/usr/local/sbin/bookpile-host-capacity-check` mode `755`, and install the
matching service/timer examples without the `.example` suffix. The lightweight
host check runs at minutes 7, 22, 37 and 52 so it does not overlap the aggregate
application check. It fails when root-disk or inode use reaches 85%, available
memory falls below 512 MiB, or 15-minute load exceeds twice the online CPU
count. Environment overrides exist for every threshold. Output is aggregate
JSON only; it contains no paths below `/`, process names or user data.

The external `BOOKPILE staging - capacidad del VPS` Healthchecks check uses the
same `*:7/15` UTC schedule with ten minutes of grace. Keep its bearer URL in
`/etc/bookpile/healthchecks-capacity.curl`, root-owned and mode `600`, and
install `bookpile-host-capacity-healthchecks.conf.example` as the capacity
service's `10-healthchecks.conf` drop-in. Disk includes Docker layers/build
cache because Docker is stored on the root filesystem. Zero swap is reported
as evidence but is not itself unhealthy; decide swap separately from alerting.

### Privacy-safe defensive metrics

Install the D5 host collector and its 15-minute systemd schedule:

```bash
sudo install -o root -g root -m 0755 \
  server/deploy/collect-defensive-metrics.py \
  /usr/local/sbin/bookpile-defensive-metrics
sudo install -o root -g root -m 0644 \
  server/deploy/systemd/bookpile-defensive-metrics.service.example \
  /etc/systemd/system/bookpile-defensive-metrics.service
sudo install -o root -g root -m 0644 \
  server/deploy/systemd/bookpile-defensive-metrics.timer.example \
  /etc/systemd/system/bookpile-defensive-metrics.timer
sudo systemctl daemon-reload
sudo systemd-analyze verify \
  bookpile-defensive-metrics.service bookpile-defensive-metrics.timer
sudo systemctl enable --now bookpile-defensive-metrics.timer
sudo systemctl start bookpile-defensive-metrics.service
sudo systemctl status bookpile-defensive-metrics.service --no-pager -l
```

The root-owned collector reads the minimized API journal, the Caddy `/data`
volume and an application-generated aggregate of recent lease events. It emits
one aggregate-only JSON record and exits non-zero if any source cannot be read
or validated. Inspect only that normalized output:

```bash
sudo journalctl -u bookpile-defensive-metrics.service \
  --since "20 minutes ago" -o cat --no-pager | tail -n 5
```

Confirm all seven names in `docs/DEFENSIVE_METRIC_CATALOGUE.md` are present,
including zero-valued families. Reject the rehearsal if output contains an IP,
`client_key`, request URL/query, identifier or private value.

The binding warning/critical table and response ownership are in
`docs/DEFENSIVE_METRIC_CATALOGUE.md`. Configure two Healthchecks checks named
`BOOKPILE staging - D5 warning` and `BOOKPILE staging - D5 critical`, both with
cron `4,19,34,49 * * * *`, UTC, ten minutes of grace and the verified
operator-email integration. This mirrors the systemd schedule and also alerts
when collection itself stops. Healthchecks deduplicates repeated failure pings
because email is emitted on status transition, not on every ping.

Install the evaluator beside the collector:

```bash
sudo install -o root -g root -m 0755 \
  server/deploy/evaluate-defensive-alerts.py \
  /usr/local/sbin/bookpile-defensive-alerts
```

For each check, copy the matching `warning` or `critical` open/recovery curl
examples from `server/deploy/`, replace only the UUID, and install the resulting
four files in `/etc/bookpile` with owner `root:root` and mode `600`. The open
configuration uses the check's `/fail` URL; recovery uses the same UUID without
`/fail`. Never paste these bearer URLs into source, logs or chat.

Reinstall `bookpile-defensive-metrics.service.example`, run `daemon-reload` and
verify the unit. Its pipeline now records the normalized metric document and a
second aggregate alert-evaluation document. A notification failure fails the
oneshot; the missed scheduled ping then remains externally visible.

Before acceptance, use disposable fixture totals to prove exactly one warning,
one critical alert, no duplicate mail on a second identical evaluation and
recovery of both channels. Confirm the warning and critical email receipts and
their recovery receipts contain only aggregate metric names and counts. Restore
healthy state and remove all fixture input afterward.

### Staging D5 metric-source acceptance — 2026-10-28

Revision `3aa18f68be231be8530a1a81bad8c9c1202338ad` installed the root-owned
collector and its `*:4/15` timer after verified backup
`df837c4d-3eeb-43c7-9872-5e3b659ef4af`. Unit verification was silent and both
manual collections completed with `0/SUCCESS`. The initial output contained
all seven aggregate metric families with zero totals. A single controlled
`/.env` request returned `404`; the following collection contained one
`scanner_probes` event attributed to fixed scope `scanner_probe` and the exact
deployed revision.

An independent parser accepted the exact metric-name set, the 15-minute window,
the five-failure validation threshold and `privacy=aggregate_only`, and rejected
the presence of client keys, raw addresses, authorization/cookie/query fields
or user/library/object identifiers. Deep reconciliation remained healthy at
438 expected and 438 stored objects. This accepts the D5 metric source only.
Warning/critical thresholds, notification delivery/deduplication/recovery and
the future administrator view remain unaccepted. `temporary_bans=0` is the
expected pre-D6 state, not evidence of an enabled edge ban.

### External server error reporting

BOOKPILE uses a separate Sentry project in the EU region for unexpected API
and email-worker exceptions. Configure only
`BOOKPILE_SERVER_ERROR_REPORTING_DSN`; keep the DSN in the protected runtime
environment and never commit or paste it into logs or chat. The integration is
deliberately manual: Sentry's default and auto-enabled integrations, tracing,
breadcrumbs, request bodies, local variables and default PII collection are
disabled. Source-code context is also disabled so stack frames cannot transmit
nearby source literals.

Every event passes through an application-owned final scrubber. It removes the
request, user, breadcrumbs, contexts, extras, log message, hostname and thread
fields; replaces exception messages with `[redacted]`; and discards every tag
except the `bookpile.*` correlation, component and deployment-revision tags.
The technical exception type and stack frames remain. This prevents library
names, object keys, email addresses, URLs, queries, cookies, tokens and database
values from becoming observability data.

After deploying a configured image, send one controlled event without causing
a public failure:

```sh
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml run --rm --no-deps api \
  bookpile-error-reporting
```

The command must return `configured: true`, `sent: true` and an event ID. In
Sentry, confirm the matching event uses the expected environment/release and
contains only redacted exception text plus the three allowed BOOKPILE tags.
Exercise the email notification route from that project as well. Browser-side
telemetry is intentionally outside this server operations boundary; adding it
later requires a separate CSP, source-map, consent and privacy review.

Staging acceptance passed on 2026-09-17 at revision `bc1ac4b`. The controlled
probe reached the EU project and the operator mailbox. Inspection showed the
expected redacted exception, environment/release and three `bookpile.*` tags;
it contained no source context, user, request, breadcrumb or private data.

### External public availability

The Sentry uptime monitor `BOOKPILE staging - disponibilidad pública` actively
requests `https://staging.bookpile.gal/health/ready` from outside the VPS. The
operator confirmed it active on 2026-09-17. A successful response proves the
public DNS/TLS/Caddy path, API process, PostgreSQL connection and private-object
store together. Its JSON response contains only aggregate readiness and the
deployment revision. This complements the server-originated Healthchecks
dead-man switches, which cannot by themselves prove public reachability.

Operational JSON contains only aggregate counts, UUIDs for queued mail/backups,
revisions and states. It must not contain usernames, email addresses, object
keys, library names, request queries, tokens or decrypted payloads. Caddy access
logging remains disabled until a tested redaction format can remove query data.

## Edge and host

Caddy is the sole public process and automatically provisions HTTPS. The checked
configuration caps request bodies at 110 MB, removes server identity, applies a
strict same-origin CSP and browser isolation headers, and bounds upstream dial
time. A 15-minute response-header allowance remains temporarily necessary for
synchronous 100 MiB import inspection; background processing could lower it.

The staging IPv4 address has an active IONOS external firewall policy: only
incoming TCP 22, 80 and 443 remain allowed after removing unused 8443/8447
rules on 2026-09-16. Public readiness and a fresh SSH connection passed after
the change. UFW remains inactive; Docker-published ports can bypass UFW, so do
not treat it as a substitute for the external policy. No public 5432/8100
listeners or allow rules were observed. The operator elected to keep TCP 22
reachable from different devices. Effective `sshd -T` output on 2026-09-16
showed public-key authentication enabled and both password and keyboard-
interactive authentication disabled. No global IPv6 address was configured;
the beta will not use IPv6 or an `AAAA` record. Preserve key-only SSH,
provider MFA, unattended OS security updates with controlled reboot
notification, and separate staging and production hosts/secrets. Recheck the
IPv6 firewall if a public IPv6 address is ever assigned.

### Staging host maintenance acceptance — 2026-10-20

The controlled UTC maintenance window installed 35 pending Ubuntu/Docker
updates with no removals or held packages and rebooted staging from kernel
`6.8.0-139-generic` into Ubuntu 24.04.5 kernel `6.8.0-147-generic`. A fresh
verified backup (`bd4cabcb-edac-47a0-ab2c-c64fdbc7e595`) preceded the update.
Docker 29.9.1, containerd 2.4.2 and Compose 5.6.0 recovered all application
services automatically. Package audit, boot errors and failed systemd units
were empty; all six BOOKPILE timers survived. Public health, Healthchecks,
Sentry uptime and a 435-object deep reconciliation passed after reboot.

One redacted Sentry `OperationalError` from the email worker occurred at 19:10
UTC while Docker restarted and PostgreSQL was temporarily unavailable. It had
one event, no post-reboot recurrence and healthy worker/outbox checks, so it is
recorded as expected bounded maintenance impact rather than an application
defect.

The effective unattended policy refreshes package lists and applies the
configured Ubuntu base/security origins daily. `noble-updates`, automatic
distribution upgrades and automatic reboots remain disabled. A required reboot
is instead announced and performed manually only after a fresh verified backup,
simulated package plan, healthy pre-check and confirmation of console/SSH
recovery access; repeat the I1 post-reboot checks before closing the window.

Post-reboot listener and independent workstation evidence confirmed only TCP
22, 80 and 443 reachable. TCP 5432 and 8100 were closed/filtered, no global
IPv6 address was assigned, and key-only SSH remained effective. Public IPv6
must remain disabled until its firewall acceptance is completed.

Authentication limits are atomic PostgreSQL counters, so API workers share
them. Stock Caddy has no distributed rate-limit module; do not silently replace
this with per-process edge counters. Additional volumetric protection may be
selected with the hosting provider in 9F.

### Costly-operation limit rehearsal

Inspect the privacy-safe aggregate state of import/export limits and leases:

```sh
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml exec -T api \
  bookpile-defensive-limits status
```

After an ordinary import/export smoke test, one controlled rehearsal may cross
every costly-operation user and library threshold:

```sh
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml exec -T api \
  bookpile-defensive-limits rehearse --confirm STAGING-LIMIT-REHEARSAL
```

The rehearsal refuses production, `off` mode and missing confirmation. It uses
fresh random identifiers and creates only hashed limit buckets and aggregate
security events: no account, library, archive or object is created. In
`observe`, all requests proceed and each of the six scopes must emit
`rate_limit_observed`; in `enforce`, the final request for each synthetic user
and library must be rejected and emit `rate_limit_blocked`. Re-run `status` and
retain both JSON outputs with the deployment revision as acceptance evidence.

The general `/api/*` client-IP ceiling has a separate rollout switch:
`BOOKPILE_SERVER_GENERAL_API_LIMIT_MODE`. Keep it `off` on first deployment,
then select `observe` in staging without changing the already accepted costly-
operation mode. `bookpile-defensive-limits status` reports its
`general_api_ip` bucket/event evidence and the configured 600/minute threshold.
Only exact `/api/*` traffic is counted; public health and frontend/static paths
remain independent. Move this policy to `enforce` only after a bounded public-
path burst produces one revision-labelled observation event and normal
navigation remains healthy.

Specific interactive-operation controls have independent rollout switches:
`BOOKPILE_SERVER_BIBLIOGRAPHIC_LOOKUP_LIMIT_MODE`,
`BOOKPILE_SERVER_COVER_UPLOAD_LIBRARY_LIMIT_MODE` and
`BOOKPILE_SERVER_REARRANGEMENT_LIMIT_MODE`. Deploy them as `off`, move all
three to `observe` for the first staging rehearsal, and run:

```sh
docker compose --env-file server/.env.staging \
  -f server/compose.production.yaml exec -T api \
  bookpile-defensive-limits rehearse-specific \
  --confirm STAGING-SPECIFIC-LIMIT-REHEARSAL
```

The command uses fresh synthetic keys, never calls an external bibliographic
provider and never writes catalogue, object or physical-library data. Retain
its correlation ID, revision and five observed events. Bibliographic IP/library
and cover-library controls may then move to `enforce` and must each produce one
correlated blocked event in a second rehearsal. Keep rearrangement in `observe`
until automated normal preview/apply interaction remains below 30/user/minute
and 60/library/minute (25% of its thresholds). Roll back only the affected mode
to `observe` or `off`, recreate the API, and verify live/ready plus the relevant
normal workflow; do not delete shared counters.

Dependabot checks pinned npm, pip, GitHub Actions and Docker dependencies weekly.
No update is auto-merged: CI, migration compatibility and release review remain
mandatory. Registry-backed vulnerability scans require explicit authorization
because they disclose the dependency graph to that registry.

## Platform administration and break glass

`SYSTEM_ADMIN` is a separate platform role, not a library membership. Its
restricted web console is required before production under
`docs/adr/0017-system-admin-console.md`. It may
manage account invitations, account state, abuse controls and aggregate service
health. It must not implicitly read catalogues, maps, loans, readings, covers,
profiles or library audit contents. Owners remain the only ordinary principals
with private library authority.

Until that console passes acceptance, host-side commands remain authenticated
by OS/SSH access and production invitations are not authorized. The console is
available only to an explicitly enrolled operator, never by matching a username
or owning a library. It requires WebAuthn/FIDO2, an independent short admin
session, current step-up for sensitive actions, immutable operator audit and a
narrow backend command catalogue. It exposes normalized security/operational
events, not arbitrary raw logs, shell, Docker, SQL, environment secrets, tokens,
email content or user-private library data. Exact controls and acceptance
evidence are tracked only in `docs/BOOKPILE_MASTER_WORK_PLAN.md`.

Break-glass access is an off-host custodied operator credential used only when
normal deployment access is unavailable. It requires provider MFA, a second
person where feasible, a time-bounded incident record, immediate credential
rotation and post-incident review. It grants recovery capability, not permission
to browse user content.
