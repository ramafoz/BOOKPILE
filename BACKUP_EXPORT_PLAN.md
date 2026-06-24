# BOOKPILE Backup, Restore, and Export Plan

## Goals

- Protect the catalogue before it grows substantially.
- Keep SQLite records and cover images together.
- Make backups understandable and portable without requiring development tools.
- Prevent an accidental restore from destroying the current catalogue.
- Keep personal data local unless the user deliberately copies a backup elsewhere.

## Backup format

BOOKPILE backups will be standard ZIP files:

```text
BOOKPILE-backup-2026-06-21-153000.zip
├── manifest.json
├── bookpile.db
└── covers/
    ├── 040c4a923b824fbb84b44271a9c61554.webp
    └── a0dc9a85d69041baa908e1c16cc50323.webp
```

### `manifest.json`

The manifest will contain:

- Backup format version.
- BOOKPILE application/schema version.
- Creation timestamp.
- Number of books, bookcases, shelves, containers, and covers.
- SQLite integrity-check result.
- List of included cover filenames.
- Checksums for the database and cover files.

The ZIP format is intentionally ordinary so the contents can still be inspected
or recovered manually.

## Creating a backup

The BOOKPILE interface will provide a **Create backup** button.

The backend will:

1. Create a consistent SQLite snapshot using SQLite's backup API.
2. Run `PRAGMA integrity_check` on the snapshot.
3. Verify that every cover referenced by the database exists.
4. Generate the manifest and checksums.
5. Package the snapshot and covers into a ZIP.
6. Return it as a browser download.
7. Remove temporary working files after download preparation.

Creating a backup will not require stopping BOOKPILE.

## Restoring a backup

Restore is the high-risk operation and will be deliberately stricter.

**Implemented:** staged inspection, explicit confirmation, automatic
pre-restore backup, atomic replacement, and rollback protection.

### Validation before changing anything

The backend will:

1. Reject non-ZIP files and oversized uploads.
2. Extract into a temporary directory, never directly into `backend/data`.
3. Reject unsafe ZIP paths.
4. Validate the manifest version and required files.
5. Verify all checksums.
6. Run SQLite integrity and foreign-key checks.
7. Confirm database counts match the manifest.
8. Confirm referenced cover files exist and are valid images.
9. Reject backups from unsupported newer schema versions.

### Safety backup

Immediately before restore, BOOKPILE will create:

```text
backend/backups/pre-restore-YYYYMMDD-HHMMSS.zip
```

This backup contains the catalogue being replaced and allows manual rollback.

### Atomic replacement

Only after validation and the safety backup succeed:

1. Move the existing data aside.
2. Install the restored database and covers.
3. Run migrations if the backup uses an older supported schema.
4. Re-run integrity checks.
5. Roll back automatically if any step fails.

The UI will require explicit confirmation and show the backup's date and record
counts before enabling restore.

## CSV export

CSV is for analysis and portability, not full restoration.

One row per book will include:

- ID.
- Title.
- Author.
- Status.
- Goodreads URL.
- Notes.
- Acquisition date.
- Reading-started date.
- Read date.
- Reading-date-unknown flag.
- Original-collection flag.
- Bookcase.
- Shelf number.
- Container type.
- Layer.
- Container number.
- Position.
- Cover filename.
- Created and updated timestamps.

CSV will use UTF-8 with a BOM for reliable opening in Microsoft Excel.

## Optional later export

- Native `.xlsx` workbook.
- Separate sheets for books, bookcases, shelves, and containers.
- Human-readable location summary.

This should follow CSV rather than precede it.

## Proposed interface

Add a **Data & backups** dialog accessible from the main navigation:

- **Download full backup**
- **Export books as CSV**
- **Restore from backup**
- Last local safety-backup information
- Brief explanation that full backups include covers, while CSV does not

## Recommended implementation order

### Phase A — backup download and CSV export

- Read-only operations.
- Lowest risk.
- Gives immediate protection before more catalogue entry.

Estimated implementation and testing: 2–3 hours.

### Phase B — validated restore

- Upload, validation, safety backup, atomic replacement, and rollback.
- Requires more extensive failure-mode testing.

Estimated implementation and testing: 3–5 hours.

## Out of scope for the first version

- Automatic cloud upload.
- Scheduled unattended backups.
- Encryption or password-protected ZIP files.
- Synchronization between several active BOOKPILE installations.

These can be considered after local backup and restore are proven reliable.
