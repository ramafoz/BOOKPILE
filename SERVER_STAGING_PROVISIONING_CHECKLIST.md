# BOOKPILE isolated staging provisioning checklist

This checklist starts Phase 9F. It creates no production service and imports no
real member data. Record only account IDs, regions, non-secret resource names,
timestamps and test results; never paste credentials into this document, Git,
issues or chat.

## 1. Purchase and account boundaries

- [x] Confirm the operator-reported regular IONOS VPS charge after promotions:
  EUR 10.89 per month including VAT, confirmed on 2026-09-16.
- [ ] Record any setup fee, minimum term, cancellation process and Spain
  location for the purchased IONOS VPS in the private operator record.
- [ ] Choose monthly billing for the first rehearsal where offered.
- [x] Verify MFA is active on the IONOS, Backblaze and Dinahosting operator
  accounts. The operator confirmed all three on 2026-09-16; the original
  activation dates relative to service-credential creation were not checked.
- [ ] Save each DPA/subprocessor/export link and invoice in the private operator
  record.
- [x] Calculate the operator-reported regular monthly equivalent on
  2026-09-16: IONOS VPS EUR 10.89, Dinahosting S3 EUR 1.30,
  domain/WhoIs EUR 39.49 per year (EUR 3.29 per month), mail EUR 30.00
  per year (EUR 2.50 per month), and Backblaze B2 currently EUR 0.
  Subtotal EUR 17.98 per month, EUR 7.02 below the EUR 25 target.
  [Backblaze's first 10 GB account-wide are free](https://www.backblaze.com/cloud-storage/transaction-pricing);
  The operator confirmed on 2026-09-16 that the quoted provider charges are
  post-promotion and include VAT; current promotional bills are lower. B2
  remains usage-based, so this is not a fixed future backup bill. Recheck
  usage charges as retained data grows.

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
- [x] Accept SSH access from any operator device rather than restrict port 22
  to one source IP. On 2026-09-16, effective `sshd -T` output showed
  `pubkeyauthentication yes`, `passwordauthentication no` and
  `kbdinteractiveauthentication no`; the account/sudo password is not an SSH
  login method. `ip -6 -brief address show scope global` returned no address.
  Do not add an `AAAA` record or assign a public IPv6 address for this beta.
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
- [x] Run the exact non-empty inventory acceptance from
  `SERVER_PRIVATE_OBJECT_STORAGE.md`. On 2026-09-16, the installed
  `bookpile-private-objects audit` compared PostgreSQL with Dinahosting and
  returned `exact: true`, `expected_count: 1`, `stored_count: 1`, and empty
  missing/mismatched/orphaned lists. This used the existing staging object;
  no new synthetic image was claimed.

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
- [x] Remove the obsolete Mailjet verification and DKIM TXT records from the
  Dinahosting DNS panel. On 2026-09-16, the operator confirmed the root SPF
  did not contain `spf.mailjet.com`, removed only `mailjet._0le9e27f` and
  `mailjet._domainkey`, and reported that public staging readiness still
  responded. MX, SPF, DMARC and `default._domainkey` were left intact. Public
  DNS propagation was not independently timed; Mailjet is no longer an
  authorized sender.
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
  passed on 2026-09-15/16. On 2026-09-16, a separate external 15-minute
  operations heartbeat was configured with ten minutes of grace. Its protected
  curl configuration returned HTTP 200, Healthchecks became green, systemd
  validation passed, and a real healthy oneshot exited zero through the
  installed success-only drop-in. A separate daily deep-reconciliation check
  was then configured for 04:05 UTC with 2h15 grace. Its protected HTTP probe,
  systemd validation and real oneshot passed on 2026-09-16; the inventory was
  one expected/stored object with zero missing, mismatched or orphaned objects.
  A fourth external check now receives the host-capacity service heartbeat every
  15 minutes. Its root-disk, inode, available-memory and 15-minute-load checks,
  protected HTTP probe, systemd validation, real oneshot and timer activation
  passed on 2026-09-16. External application error reporting remains open.
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
