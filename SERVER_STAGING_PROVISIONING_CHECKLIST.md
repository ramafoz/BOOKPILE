# BOOKPILE isolated staging provisioning checklist

This checklist starts Phase 9F. It creates no production service and imports no
real member data. Record only account IDs, regions, non-secret resource names,
timestamps and test results; never paste credentials into this document, Git,
issues or chat.

## 1. Purchase and account boundaries

- [ ] Recheck the regular (not promotional) IONOS VPS M+ monthly price, setup
  fee, minimum term, cancellation process and Spain location before purchase.
- [ ] Choose monthly billing for the first rehearsal where offered.
- [ ] Enable MFA on IONOS, Backblaze and Dinahosting before
  creating service credentials.
- [ ] Save each DPA/subprocessor/export link and invoice in the private operator
  record.
- [ ] Confirm the recurring total remains below the agreed ceiling.

Recommended initial VPS: 4 vCPU, 4 GB RAM, 120 GB NVMe, current Ubuntu LTS,
Spanish region. Do not purchase Plesk, antivirus bundles or a provider backup as
a substitute for BOOKPILE's encrypted off-site backup. A provider snapshot may
be an additional convenience only.

## 2. DNS and host

- [x] Create only an `A` record for `staging.bookpile.gal` pointing to the VPS.
  Add `AAAA` only after IPv6 firewall and reachability are deliberately tested.
- [ ] Keep `bookpile.gal` unchanged and reserved for the later production gate.
- [x] Install security updates, key-only SSH, Docker Engine and Compose from
  their official repositories. On Ubuntu 24.04, run the reviewed
  `server/deploy/provision-ubuntu-host.sh` installer as the trusted administrator
  and reconnect before validating Docker access.
- [x] Verify the active IONOS external firewall policy assigned to the staging
  IPv4 address on 2026-09-16. Incoming rules now permit only TCP 22, 80 and
  443; default-denied 5432/8100 have no public listener. The unused default
  TCP 8443/8447 rules were removed, and a fresh SSH connection and public
  readiness check still passed. UFW is inactive; Docker-published ports must
  not be assumed to obey UFW rules.
- [ ] Restrict SSH to the operator network where practical, after confirming
  a stable source address and a working provider-console recovery path. Review
  any separately assigned public IPv6 address/policy before exposing IPv6.
- [ ] Create `/opt/bookpile`, check out the exact approved commit and verify the
  worktree is clean.

## 3. Active private objects in Spain

- [x] Create a private Dinahosting bucket dedicated to the isolated 1 GB
  staging account; disable sharing and anonymous/public access.
- [x] Prove the provider signing region (`us-east-1`) and path-style addressing
  against `https://objects.dinaserver.com`; do not infer them from AWS defaults.
- [x] Dinahosting support confirmed it cannot issue a distinct read-only
  credential for the same bucket. The operator explicitly accepted reuse of
  the isolated application credential for backup reads for the initial private
  beta on 2026-09-16; see the residual-risk decision in
  `SERVER_PRIVATE_OBJECT_STORAGE.md`.
- [x] Create an isolated application account/credential capped to 1 GB. Its
  effective put/stat/read/list/delete access and metadata preservation passed a
  1,024-byte round trip under the `staging` prefix on 2026-09-13; the probe
  object was deleted. An unauthenticated bucket request returned `403
  AccessDenied`.
- [x] Decide the backup-reader credential gap for the initial private beta:
  accept the provider's write-capable credential reuse, without claiming that
  the backup process has provider-enforced read-only access. Reassess if the
  provider adds scoped read-only keys or the threat model changes.
- [x] Copy `server/.env.staging.example` to `.env.staging`, fill the endpoint,
  region and credentials, and set mode `600`.
- [x] Run `bookpile-private-objects probe` before application startup. It
  returned `{"ready": true, "verified_bytes": 1024}` against Dinahosting.
- [ ] Run the exact non-empty inventory acceptance from
  `SERVER_PRIVATE_OBJECT_STORAGE.md` after adding a synthetic private image.

## 4. Immutable backup in a separate EU failure domain

- [x] Create a Backblaze account in **EU Central**; region selection is fixed at
  account creation.
- [x] Create a private, encrypted disposable acceptance bucket with Object Lock
  enabled at `s3.eu-central-003.backblazeb2.com`. Never test lock policy first
  on the final 29-day prefix.
- [x] Use a disposable acceptance prefix/bucket to prove a short COMPLIANCE
  retention cannot be bypassed and that deletion succeeds after expiry. On
  2026-09-13, `bookpile-operational-backup probe-lock` verified a 1,024-byte
  version and proved that Backblaze rejected its deletion through
  2026-09-14 18:04 UTC. After expiry,
  `delete-expired-lock-probe` deleted that exact version and verified it was
  absent. Targeting the version ID prevented a delete marker from producing a
  false pass.
- [x] Create the `bookpile-staging-backups-2026` private encrypted EU Central
  bucket with Object Lock and a bucket-scoped `staging/` application key.
  Exact capability minimization and final lifecycle expiry remain to be checked.
- [x] Copy `.env.staging.backup.example` to `.env.staging.backup`, set mode
  `600`, and keep its encryption secret in an off-host password manager.

## 5. Transactional email and alerts

- [x] Provision and authenticate the staging-only `hello@bookpile.gal`
  Dinahosting SMTP account over implicit TLS on port 465; keep its credential
  only in `.env.staging`.
- [x] Publish Dinahosting-compatible SPF, enable its DKIM and retain a deliberate
  relaxed-alignment `p=none` DMARC observation policy. Add a private aggregate-
  report destination before production.
- [x] Deliver a real verification message through the durable worker and
  complete the account-verification link. The worker recorded `SENT` on its
  first attempt on 2026-09-14.
- [ ] Remove the obsolete Mailjet verification and DKIM DNS records after
  recording final DNS evidence; Mailjet is no longer an authorized sender.
- [x] Select `ramafoz@gmail.com` as the private external operator mailbox.
  The daily backup check received a success ping after a verified systemd
  backup on 2026-09-15. A disposable check then sent a controlled failure
  alert to this mailbox on 2026-09-16; the disposable check was removed.
- [x] Exercise a real password-reset message and one-time link for the verified
  staging account on 2026-09-16. The operator confirmed the new password signs
  in and the old password is rejected; no link, token or password was recorded.
- [ ] Exercise deletion-recovery messages, an induced temporary SMTP failure
  with retry, and a terminal outbox failure alert.

## 6. First deployment and evidence

- [x] Follow `SERVER_PRODUCTION_RUNBOOK.md` through Compose preflight, explicit
  migration, API/worker/web startup and public readiness. On 2026-09-14 the
  verified account created its first library at revision `ad9a16a`, proving the
  authenticated CSRF-protected write path.
- [x] Install and manually prove the backup-daily, 15-minute backup-freshness,
  hourly retention-maintenance, 15-minute lightweight-operations and daily
  deep-object-reconciliation systemd timers. Their 2026-09-15 oneshots
  succeeded; checks were `healthy: true` and the deep inventory was one exact
  object. The external backup heartbeat and a disposable alert-delivery test
  passed on 2026-09-15/16. Broader operations failure alerting remains open.
- [x] Prove unattended daily execution: systemd created and verified backup
  `0ec5ab57-56c0-4887-b375-20f12fe1280c` at 02:17 UTC on 2026-09-15,
  including one private object.
- [x] Create and independently verify an encrypted backup with one private
  object. Backup `276b0264-4aad-43ff-b9fc-591984cbbe77` restored 36 tables
  and one exact object into a disposable PostgreSQL database and empty local
  volume on 2026-09-14. The disposable container, volumes and network were
  removed. A second verified backup ran successfully through systemd.
- [ ] Record RPO/RTO, CPU, peak memory, free disk, request/import/backup/restore
  durations and every provider gap in the private staging evidence record.
- [ ] Destroy disposable acceptance resources and rotate any credentials used
  by destructive tests.

Passing this list closes provider gates in 9A-9E and the measured 9F rehearsal.
It does not switch the apex domain, invite beta users or authorize production.
