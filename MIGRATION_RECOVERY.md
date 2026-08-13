# Database migration and recovery

BOOKPILE uses versioned, transactional SQLite migrations for database changes
that cannot be represented by the original catalogue schema. The first such
change is schema v2, which adds nullable, non-unique, indexed ISBN-10 and
ISBN-13 fields. Schema v3 adds only nullable bibliographic metadata fields and
controlled classifications. Existing book values are not rewritten.

## Safety guarantees

Before a pending migration is allowed to write, BOOKPILE:

1. Checks SQLite integrity and foreign-key consistency.
2. Takes a deterministic snapshot of all fields and records that existed in
   the source schema, including ISBN values when migrating from v2.
3. Creates a complete ZIP containing the database and every referenced cover.
4. Validates that ZIP using the same checksum, image, count, and schema checks
   as the restore feature.
5. Applies all schema statements inside one `BEGIN IMMEDIATE` transaction.
6. Rechecks integrity, foreign keys, schema version, and every pre-existing
   catalogue value before committing.

Any exception rolls back the database transaction. The pre-migration ZIP is
retained even when the transaction fails. A schema newer than the running app
is rejected rather than guessed at.

## Inspect without changing anything

Stop BOOKPILE before performing maintenance. From the project root, run:

```powershell
backend\.venv\Scripts\python.exe maintenance\migrate_database.py
```

This command is read-only unless `--approve` is supplied. It reports the
current schema and the exact pending migrations.

## Rehearse against a backup

Create a fresh full backup from **Settings → Data & backups**, then run:

```powershell
backend\.venv\Scripts\python.exe maintenance\rehearse_database_migration.py `
  backend\backups\YOUR-BACKUP.zip
```

The script validates and extracts the backup into a temporary directory,
migrates only that disposable copy, compares old values before and after,
builds and validates a post-migration backup, prints a JSON report, and deletes
the temporary files. It never opens the live database.

A rehearsal is acceptable only when it reports:

- `live_database_opened: false`
- `existing_values_preserved: true`
- matching catalogue fingerprints before and after
- `integrity_check: ok`
- zero foreign-key errors
- unchanged catalogue and cover counts
- a validated post-migration backup at the target schema

## Apply an approved migration

Do this only after a successful rehearsal and with the app stopped:

```powershell
backend\.venv\Scripts\python.exe maintenance\migrate_database.py --approve
```

The command writes its mandatory verified backup to `backend/backups/` with a
name such as `BOOKPILE-pre-migration-v1-....zip`. Keep both that file and the
separate user-created backup until the migrated catalogue has been checked in
the UI. Running the command again is safe: when no migration is pending it
does not create another backup or alter the database.

Migrations are deliberately not triggered by the development server's reload
cycle. This prevents saving backend code from silently migrating the live
catalogue.

## Recovery after a failed migration

If the command reports an error, do not rerun it repeatedly and do not delete
the automatic ZIP. The SQLite transaction should already have rolled back.

1. Leave BOOKPILE stopped.
2. Run the read-only inspection command and retain its output.
3. Preserve the newest `BOOKPILE-pre-migration-...zip` elsewhere as a second
   copy.
4. Start the unchanged app and use **Settings → Data & backups → Restore** to
   inspect and restore the verified pre-migration ZIP.
5. If the UI cannot start, preserve the current `backend/data/` directory
   before doing anything else. Restore through the tested backend restore
   workflow after returning to the last compatible code revision; do not
   manually mix a database from one backup with covers from another.

The restore workflow itself makes another `pre-restore-...zip` before replacing
the catalogue and rolls back both the database and covers if verification
fails.

## Backup compatibility rule

Each ZIP manifest records the schema actually present in its database. The app
accepts backups at or below its latest supported schema and rejects newer ones.
Old backups remain source-of-truth archives. During restore, an older schema is
migrated and verified while it is still an isolated incoming copy, before it
can replace the live catalogue. This produces both the normal pre-restore ZIP
of the current catalogue and the migration runner's verified ZIP of the older
incoming catalogue.
