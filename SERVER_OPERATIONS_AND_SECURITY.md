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

Example systemd units and timers live in `server/deploy/systemd`: backup daily,
maintenance hourly, lightweight checks every 5 minutes, backup freshness every
15 minutes and full private-object reconciliation daily.

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

### External server error reporting

BOOKPILE uses a separate Sentry project in the EU region for unexpected API
and email-worker exceptions. Configure only
`BOOKPILE_SERVER_ERROR_REPORTING_DSN`; keep the DSN in the protected runtime
environment and never commit or paste it into logs or chat. The integration is
deliberately manual: Sentry's default and auto-enabled integrations, tracing,
breadcrumbs, request bodies, local variables and default PII collection are
disabled.

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

Authentication limits are atomic PostgreSQL counters, so API workers share
them. Stock Caddy has no distributed rate-limit module; do not silently replace
this with per-process edge counters. Additional volumetric protection may be
selected with the hosting provider in 9F.

Dependabot checks pinned npm, pip, GitHub Actions and Docker dependencies weekly.
No update is auto-merged: CI, migration compatibility and release review remain
mandatory. Registry-backed vulnerability scans require explicit authorization
because they disclose the dependency graph to that registry.

## Platform administration and break glass

`SYSTEM_ADMIN` is a future platform role, not a library membership. It may
manage account invitations, account state, abuse controls and aggregate service
health. It must not implicitly read catalogues, maps, loans, readings, covers,
profiles or library audit contents. Owners remain the only ordinary principals
with private library authority.

The first staging/beta cut intentionally has no web `SYSTEM_ADMIN` panel.
Host-side commands are authenticated by OS/SSH access. A future friendly
operator panel is planned for an explicitly enrolled operator, not granted
by matching the username `ramafoz` or by owning a library. Before UI work,
it requires independent authentication, MFA or step-up for sensitive actions,
immutable operator audit and a narrow backend command catalogue. It must not
expose shell, Docker, environment secrets or user-private library data.

Break-glass access is an off-host custodied operator credential used only when
normal deployment access is unavailable. It requires provider MFA, a second
person where feasible, a time-bounded incident record, immediate credential
rotation and post-incident review. It grants recovery capability, not permission
to browse user content.
