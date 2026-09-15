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
listeners or allow rules were observed. SSH is still allowed from all sources;
restrict it to the operator's protected network if a stable address and a
provider-console recovery path are available. Review any separately assigned
IPv6 address/policy before exposing IPv6. Use key-only SSH, provider MFA,
unattended OS security updates with controlled reboot notification, and
separate staging and production hosts/secrets. SSH source restriction remains
a Phase 9F decision.

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
