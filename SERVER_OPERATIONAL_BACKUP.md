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

Copy `server/.env.backup.example` to `server/.env.backup`, mode `600`. This file
is supplied only to the backup container. Use:

- a PostgreSQL login limited to connect/read for `pg_dump`;
- an active-object credential limited to list/get;
- a separate off-site credential limited to list/get/put and deletion after
  retention (or let provider lifecycle perform deletion);
- an independent random encryption key of at least 32 characters.

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
- A clean disposable PostgreSQL database restored 36 tables and a separate
  disposable S3-compatible bucket restored all 869 objects with exact hashes.
- The disposable restore database, bucket/container and local staging were
  removed after the rehearsal; source data was read-only.

Real-provider Object Lock/lifecycle behaviour and the Spanish staging disaster
drill remain Phase 9F gates.
