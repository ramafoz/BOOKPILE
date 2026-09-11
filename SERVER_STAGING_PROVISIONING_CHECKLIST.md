# BOOKPILE isolated staging provisioning checklist

This checklist starts Phase 9F. It creates no production service and imports no
real member data. Record only account IDs, regions, non-secret resource names,
timestamps and test results; never paste credentials into this document, Git,
issues or chat.

## 1. Purchase and account boundaries

- [ ] Recheck the regular (not promotional) IONOS VPS M+ monthly price, setup
  fee, minimum term, cancellation process and Spain location before purchase.
- [ ] Choose monthly billing for the first rehearsal where offered.
- [ ] Enable MFA on IONOS, Arsys, Backblaze, Mailjet and Dinahosting before
  creating service credentials.
- [ ] Save each DPA/subprocessor/export link and invoice in the private operator
  record.
- [ ] Confirm the recurring total remains below the agreed ceiling.

Recommended initial VPS: 4 vCPU, 4 GB RAM, 120 GB NVMe, current Ubuntu LTS,
Spanish region. Do not purchase Plesk, antivirus bundles or a provider backup as
a substitute for BOOKPILE's encrypted off-site backup. A provider snapshot may
be an additional convenience only.

## 2. DNS and host

- [ ] Create only an `A` record for `staging.bookpile.gal` pointing to the VPS.
  Add `AAAA` only after IPv6 firewall and reachability are deliberately tested.
- [ ] Keep `bookpile.gal` unchanged and reserved for the later production gate.
- [ ] Install security updates, key-only SSH, Docker Engine and Compose from
  their official repositories. On Ubuntu 24.04, run the reviewed
  `server/deploy/provision-ubuntu-host.sh` installer as the trusted administrator
  and reconnect before validating Docker access.
- [ ] Restrict SSH to the operator network where practical; allow inbound
  80/443 and deny public 5432/8100.
- [ ] Create `/opt/bookpile`, check out the exact approved commit and verify the
  worktree is clean.

## 3. Active private objects in Spain

- [ ] Create a private Arsys bucket dedicated to staging; disable website and
  anonymous/public access.
- [ ] Create one application credential restricted to list/get/put/delete only
  under the staging prefix.
- [ ] Create a distinct backup-reader credential restricted to list/get only.
- [ ] Copy `server/.env.staging.example` to `.env.staging`, fill the endpoint,
  region and credentials, and set mode `600`.
- [ ] Run `bookpile-private-objects probe`, then the exact inventory acceptance
  from `SERVER_PRIVATE_OBJECT_STORAGE.md` before application startup.

## 4. Immutable backup in a separate EU failure domain

- [ ] Create a Backblaze account in **EU Central**; region selection is fixed at
  account creation.
- [ ] Create the backup bucket with Object Lock enabled. Never test lock policy
  first on the final 29-day prefix.
- [ ] Use a disposable acceptance prefix/bucket to prove a short COMPLIANCE
  retention cannot be bypassed and that deletion succeeds after expiry.
- [ ] Create a bucket-scoped application key with only the capabilities needed
  by create/verify/prune/restore.
- [ ] Copy `.env.staging.backup.example` to `.env.staging.backup`, set mode
  `600`, and keep its encryption key in an off-host password manager.

## 5. Transactional email and alerts

- [ ] Add and authenticate `bookpile.gal` in Mailjet using Dinahosting DNS.
- [ ] Publish the provider's SPF and DKIM records and a deliberate DMARC policy;
  wait for provider validation before sending account links.
- [ ] Create a staging-only SMTP/API credential and put it only in
  `.env.staging`.
- [ ] Select a private operator mailbox for TLS notices, failed systemd units,
  failed outbox delivery and backup freshness.
- [ ] Exercise verification, reset and deletion-recovery messages, including an
  induced temporary SMTP failure and a terminal failure alert.

## 6. First deployment and evidence

- [ ] Follow `SERVER_PRODUCTION_RUNBOOK.md`: Compose preflight, explicit
  migration, API/worker/web startup, readiness and synthetic smoke path.
- [ ] Install the example systemd timers and prove each oneshot command both
  succeeds normally and produces an observable failed unit.
- [ ] Create and verify a backup, then restore it into a clean disposable
  PostgreSQL database and empty disposable bucket.
- [ ] Record RPO/RTO, CPU, peak memory, free disk, request/import/backup/restore
  durations and every provider gap in the private staging evidence record.
- [ ] Destroy disposable acceptance resources and rotate any credentials used
  by destructive tests.

Passing this list closes provider gates in 9A-9E and the measured 9F rehearsal.
It does not switch the apex domain, invite beta users or authorize production.
