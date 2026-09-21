# BOOKPILE Server operational backup and recovery

## What this protects

The operational snapshot protects the entire Server service: one consistent
PostgreSQL custom dump plus every private object referenced by that database
(covers and profile images). It is separate from user-downloadable ZIP exports,
does not count against user quota and is never exposed through the web API.

The database dump is made from an exported repeatable-read snapshot. Object
keys, hashes, table counts, schema revision and deployment revision live in an
encrypted manifest. The only plaintext off-site record is a completion marker
containing a random backup UUID, timestamp, format version, key ID and encrypted
manifest hash. A marker is uploaded last; an interrupted upload is not a backup.

Every artefact is encrypted locally in independently authenticated 1 MiB
AES-GCM chunks before upload. The encryption secret never enters PostgreSQL,
the active-object bucket, Git or an image. The backup image is non-root and is
separate from the API and email worker.

## Required storage policy

Use a bucket in a failure domain separate from the active private-object bucket.
Enable versioning, S3 Object Lock at bucket creation and provider lifecycle
deletion. BOOKPILE writes objects in `COMPLIANCE` mode for 29 days; lifecycle
must permanently expire versions after the lock releases and no later than the
documented 30-day operational ceiling. Test provider semantics before staging.

Before using a final backup bucket, set up a disposable Object Lock bucket and
temporary bucket/prefix-scoped key. Configure a one-day retention and run:

```bash
docker run --rm --env-file ~/bookpile-b2-lock-probe.env \
  bookpile-api:phase9 bookpile-operational-backup probe-lock
```

The command uploads 1,024 random bytes, verifies their hash, size, version ID,
future COMPLIANCE expiry and then attempts to delete that exact version. It
succeeds only when deletion is denied and the protected version remains. Keep
the returned key/version receipt. After its recorded expiry, delete and verify
that exact version with the same temporary environment:

```bash
docker run --rm --env-file ~/bookpile-b2-lock-probe.env \
  bookpile-api:phase9 bookpile-operational-backup \
  delete-expired-lock-probe PROBE_KEY PROBE_VERSION_ID
```

The cleanup command rejects every key outside BOOKPILE's generated
`_compliance-probe/` namespace and refuses a version whose COMPLIANCE retention
has not expired. After it returns `{"deleted": true, ...}`, remove the
disposable bucket and temporary key.

Copy `server/.env.backup.example` to `server/.env.backup`, mode `600`. This file
is supplied only to the backup container. Use:

- a PostgreSQL login limited to connect/read for `pg_dump`;
- an active-object credential limited to list/get;
- a separate off-site credential limited to list/get/put and deletion after
  retention (or let provider lifecycle perform deletion);
- an independent random encryption key of at least 32 characters.

The backup CLI rejects missing, short and built-in development encryption
secrets before accessing the remote repository, even if a custom key ID is set.

Keep the encryption key and its non-secret key ID in an off-host password
manager/recovery record. Retain an old key until every snapshot bearing its ID
has expired. Losing the key makes compliant snapshots intentionally
unrecoverable.

Create the database reader while connected as the database owner, substituting
a generated password. Repeat the default-privilege grants after changing the
role that owns future migrations:

```sql
CREATE ROLE bookpile_backup LOGIN PASSWORD 'generated-secret';
GRANT CONNECT ON DATABASE bookpile TO bookpile_backup;
GRANT USAGE ON SCHEMA public TO bookpile_backup;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO bookpile_backup;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO bookpile_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE bookpile IN SCHEMA public
  GRANT SELECT ON TABLES TO bookpile_backup;
ALTER DEFAULT PRIVILEGES FOR ROLE bookpile IN SCHEMA public
  GRANT SELECT ON SEQUENCES TO bookpile_backup;
```

## Create, verify and retain

The one-shot Compose profile is suitable for a systemd timer:

```bash
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml --profile operations run --rm backup create
```

Creation always downloads and decrypts every uploaded artefact before returning
success, then prunes completed snapshots older than the configured 29 days.
Progress is emitted as JSON without object keys or user data. Save the final
line, especially `backup_id`, in the operations log.

Independent verification is read-only:

```bash
docker compose --env-file server/.env.production \
  -f server/compose.production.yaml --profile operations run --rm \
  backup verify BACKUP_UUID
```

Install the example unit/timer from `server/deploy/systemd`, adjusting
`WorkingDirectory`. The account allowed to control Docker is effectively a host
administrator and must be protected accordingly. Alert if no verified snapshot
finishes within 25 hours; scheduling/alerts are completed in Phase 9E.

## Restore drill or total-host recovery

Restoration has no in-place mode. Prepare a PostgreSQL database with **no public
tables** and an empty private-object bucket. Supply target credentials through a
temporary root-readable environment file using the `BOOKPILE_RESTORE_*` names
implemented by the CLI. Never put recovery secrets in command arguments.

```bash
docker run --rm \
  --network bookpile-production_backend \
  --env-file server/.env.backup \
  --env-file /root/bookpile-restore.env \
  bookpile-backup:phase9 restore BACKUP_UUID --apply
```

The command downloads and authenticates all content before writing anything,
rechecks both destinations, writes verified objects, and runs PostgreSQL 17
`pg_restore --single-transaction`. It then compares every application table
count and the complete object inventory/hashes. On database failure, newly
written target objects are removed. On a final invariant failure, discard both
recovery targets and start again; never point DNS or application credentials at
an unverified restore.

After success, configure a fresh application deployment for the restored
database/bucket, run readiness and smoke checks, rotate temporary recovery
credentials, and securely delete the restore environment file.

## Local evidence (2026-09-11)

- Corruption, truncation, cross-snapshot use, non-empty targets, retention and
  compensation are covered by automated tests.
- The isolated image runs as UID/GID 10001 with PostgreSQL 17.6 tools.
- A real development snapshot encrypted and verified a 412,316-byte PostgreSQL
  custom dump and 869 private objects.

## Backblaze acceptance evidence (2026-09-13/14)

- An EU Central disposable bucket preserved a 1,024-byte version, checksum,
  version ID and one-day COMPLIANCE retention timestamp.
- Deletion of the exact version was rejected before its 2026-09-14 18:04 UTC
  expiry.
- After expiry, `delete-expired-lock-probe` deleted the same version and a
  version-specific HEAD confirmed its absence. No delete-marker-only result was
  accepted.
- A clean disposable PostgreSQL database restored 36 tables and a separate
  disposable S3-compatible bucket restored all 869 objects with exact hashes.
- The disposable restore database, bucket/container and local staging were
  removed after the rehearsal; source data was read-only.

## Spanish staging recovery evidence (2026-09-14/18)

- Final bucket: `bookpile-staging-backups-2026`, private, encrypted and
  Object-Locked in EU Central; final 29-day lifecycle expiry is not yet proven.
- Backup `276b0264-4aad-43ff-b9fc-591984cbbe77` contained a 119,314-byte
  PostgreSQL custom dump and one private Dinahosting S3 object. Create and an
  independent `verify` returned `verified: true`; `status` was healthy.
- An isolated PostgreSQL 17 database and empty local object volume restored
  36 tables at `0021_email_outbox` and the exact object. The restore verified
  table counts and object inventory; disposable targets were removed.
- Systemd created a second verified snapshot
  `0598e4bc-5433-46f5-95b9-44422e9733ea`; daily and 15-minute freshness
  timers are enabled. Failure/paging tests remain open.
- PostgreSQL backup login has `SELECT` but no `INSERT`/`DELETE` on the
  application table. Dinahosting could not supply a separate read-only key
  for the same active bucket; staging temporarily reuses its isolated
  application credential as a documented least-privilege gap.
- On 2026-09-18, backup `623c595c-2aa7-44db-903c-c833c647120b` independently
  verified its PostgreSQL dump and 434 private objects before a measured
  total-host-loss rehearsal. At the simulated incident time its age was
  23,782 seconds (RPO 6 h 36 min 22 s), inside the initial 24-hour target.
- Empty isolated targets restored 36 tables at `0021_email_outbox` and all 434
  objects with exact inventory and hashes. The current API image then migrated
  the restored database to `0022_email_delivery_receipts` in 1.70 seconds. A
  read-only object audit reported 434 expected/stored objects and zero missing,
  mismatched or orphaned objects.
- The successful restore itself took 311.48 seconds (5 min 11.48 s). The
  recovered API completed startup about eight seconds after it was started and
  returned readiness with both `database` and `private_objects` ready.
- End-to-end RTO from the first restore attempt at 21:43:34 UTC to recovered
  API startup at 22:19:22 UTC was 2,148 seconds (35 min 48 s), including
  diagnosis and correction of the rehearsal defects below. This is comfortably
  inside the initial four-hour target.
- The rehearsal exposed three runbook prerequisites: the restore container
  needs both the private database network and controlled egress to Backblaze;
  Backblaze Class B transactions must not be capped during recovery; and a
  filesystem restore target must be writable by the image UID/GID 10001. The
  provider transaction limit was removed after pay-as-you-go was confirmed,
  and the target volume was recreated with owner 10001 and mode 0700.
- Host disk use increased by approximately 49,799,168 bytes (47.5 MiB) after
  restore. The host had four CPUs and about 2.73 GB available memory before the
  run; steady-state available memory changed by only about 6 MB. Peak memory
  was not captured, so no peak claim is made and a future larger-dataset drill
  should sample it during execution.
- The disposable API/container, PostgreSQL database and object volume were
  removed after validation. The active staging database and private-object
  store were never restore targets. A final deep check after cleanup returned
  `healthy: true`: database, deletion cleanup, email outbox and private objects
  were ready; all overdue/failed counters were zero; and the active inventory
  still contained 434 expected/stored objects with zero missing, mismatched or
  orphaned objects.

The measured RPO/RTO and external alerting gates have passed. Final lifecycle
expiry evidence and consolidation of the private provider/cost record remain;
neither the apex domain nor production data has been switched.
