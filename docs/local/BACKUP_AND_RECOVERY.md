# Backup and recovery for BOOKPILE Local v1

Your catalogue is local. BOOKPILE does not automatically copy it to a cloud
service, so a deliberate backup routine is essential.

## The backup to keep

Use **Settings → Data & backups → Download full backup**. The resulting ZIP is
the only restorable export format. It contains:

- the SQLite catalogue;
- all referenced cover images;
- format and database-schema versions;
- record counts and SHA-256 checksums used during validation.

CSV exports are useful for inspection and spreadsheets, but they are not a
complete backup and cannot be restored into BOOKPILE.

## Recommended routine

- Make a full ZIP backup after a substantial cataloguing session.
- Make one immediately before updating BOOKPILE or restoring another backup.
- Keep at least two generations in a folder outside the BOOKPILE installation.
- Keep a second copy on another physical device or a reputable cloud-storage
  account.
- Do not edit files inside the ZIP.
- Use descriptive filenames or folders that preserve the creation date.

A backup stored only under `backend/backups` remains on the same disk as the
live catalogue and does not protect against disk loss.

## Restore safely

1. Stop other BOOKPILE windows or devices from editing the catalogue.
2. Open **Settings → Data & backups**.
3. Select the full ZIP and request validation.
4. Review the detected schema, creation time, and record counts.
5. Confirm restoration only if the summary matches the expected library.

BOOKPILE stages and validates the archive, creates an automatic safety backup,
then replaces the database and covers together. If replacement fails, it rolls
back to the previous data. A successful restore replaces the current local
catalogue; it does not merge two catalogues.

## Manual emergency copy

When the application cannot start, stop BOOKPILE and copy the entire
`backend\data` folder to a safe external location before troubleshooting. This
is an emergency preservation copy, not the preferred portable backup format.
Do not manipulate `bookpile.db` while BOOKPILE is running.

For developer-level migration and rollback details, see
[MIGRATION_RECOVERY.md](MIGRATION_RECOVERY.md).
