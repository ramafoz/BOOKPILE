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
- [ ] Restrict SSH to the operator network where practical; allow inbound
  80/443 and deny public 5432/8100.
- [ ] Create `/opt/bookpile`, check out the exact approved commit and verify the
  worktree is clean.

## 3. Active private objects in Spain

- [x] Create a private Dinahosting bucket dedicated to the isolated 1 GB
  staging account; disable sharing and anonymous/public access.
- [x] Prove the provider signing region (`us-east-1`) and path-style addressing
  against `https://objects.dinaserver.com`; do not infer them from AWS defaults.
- [ ] Confirm whether Dinahosting can issue a distinct read-only credential for
  the same bucket. Record a provider gap and stop before production acceptance
  if application-key reuse would otherwise be required.
- [x] Create an isolated application account/credential capped to 1 GB. Its
  effective put/stat/read/list/delete access and metadata preservation passed a
  1,024-byte round trip under the `staging` prefix on 2026-09-13; the probe
  object was deleted. An unauthenticated bucket request returned `403
  AccessDenied`.
- [ ] Create a distinct backup-reader credential restricted to list/get only.
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
- [ ] Use a disposable acceptance prefix/bucket to prove a short COMPLIANCE
  retention cannot be bypassed and that deletion succeeds after expiry. On
  2026-09-13, `bookpile-operational-backup probe-lock` verified a 1,024-byte
  version and proved that Backblaze rejected its deletion through
  2026-09-14 18:04 UTC. Deletion after expiry remains to be proved before this
  item can close. The probe targets the returned version ID so a versioning
  delete marker cannot produce a false pass.
- [ ] Create a bucket-scoped application key with only the capabilities needed
  by create/verify/prune/restore.
- [ ] Copy `.env.staging.backup.example` to `.env.staging.backup`, set mode
  `600`, and keep its encryption key in an off-host password manager.

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
- [ ] Select a private operator mailbox for TLS notices, failed systemd units,
  failed outbox delivery and backup freshness.
- [ ] Exercise password-reset and deletion-recovery messages, including an
  induced temporary SMTP failure and a terminal failure alert.

## 6. First deployment and evidence

- [x] Follow `SERVER_PRODUCTION_RUNBOOK.md` through Compose preflight, explicit
  migration, API/worker/web startup and public readiness. On 2026-09-14 the
  verified account created its first library at revision `ad9a16a`, proving the
  authenticated CSRF-protected write path.
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
