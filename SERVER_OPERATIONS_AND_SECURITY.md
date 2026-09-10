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

At the VPS firewall, allow inbound TCP 22 only from the operator's protected
network where practical and 80/443 from the internet. Deny 5432, 8100 and all
Docker internal-network ports. Use key-only SSH, provider MFA, unattended OS
security updates with controlled reboot notification, and separate staging and
production hosts/secrets. Exact commands depend on the selected Spanish VPS and
are a Phase 9F rehearsal item.

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

The beta intentionally has no web `SYSTEM_ADMIN` panel. Host-side commands are
authenticated by OS/SSH access. A future admin domain requires independent
authentication and immutable operator audit before UI work begins.

Break-glass access is an off-host custodied operator credential used only when
normal deployment access is unavailable. It requires provider MFA, a second
person where feasible, a time-bounded incident record, immediate credential
rotation and post-incident review. It grants recovery capability, not permission
to browse user content.
