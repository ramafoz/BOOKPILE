# BOOKPILE Server Phase 8 — Import, export, and recovery

## Objective

Phase 8 makes one library portable without treating a Local SQLite database as
a Server database. A validated Local v1 ZIP is converted into canonical
records and then consolidated into one selected Server library. Server exports
contain only that library and its permitted member-owned data; they never
contain credentials, sessions, account profiles, or unrelated libraries.

## Delivery slices

### 8A — Local ZIP inspection and adapter foundation

- Enforce a 100 MiB compressed upload limit, bounded entry count, bounded
  expanded size, suspicious compression-ratio checks, safe paths, and no
  encrypted entries or links.
- Validate the manifest, exact file list, sizes, SHA-256 checksums, SQLite
  integrity and foreign keys, record counts, referenced covers, and WebP image
  contents in isolated temporary storage.
- Select the source adapter by `(backup_format_version, schema_version)`.
- Support the published Local backup format 1 / schema 8 first and emit a
  deterministic, non-sensitive preflight report without writing Server data.

### 8B — Authenticated preflight jobs

- Add short-lived import jobs owned by the uploading Owner.
- Let the Owner select an existing destination library or create a new one,
  and select exactly one current Owner to receive Local personal readings and
  Goodreads links.
- Report source counts, warnings, duplicate candidates, cover processing,
  estimated final logical storage, and fatal incompatibilities.
- Fingerprint archives and require an explicit decision for a repeated import.

Temporary quarantine and processing bytes are operational workspace and are
not charged to an account. The final logical Server representation is checked
against the shared Owner quota before consolidation.

### 8C — Atomic Local-to-Server consolidation

- Generate fresh UUIDs and explicit source-ID maps.
- Import hierarchy, books, ordered authors, placement and map geometry.
- Assign readings and personal Goodreads links only to the selected Owner.
- Import shared loan history with existing Owner/Viewer projections.
- Process covers through private object storage.
- Lock destination/quota state, validate post-import counts and relationships,
  and commit once. Any database or object-storage failure leaves no visible
  partial import and removes compensating objects.

Duplicate ISBN/title candidates are warnings, not automatic merges. Import is
additive unless the later restore workflow explicitly says otherwise.

### 8D — Server-portable library export

- Define a versioned canonical Server ZIP with manifest and checksums.
- Export one selected library, its physical/map data, cover objects, loans,
  and personal reading/review records labelled by stable member references.
- Exclude passwords, tokens, sessions, email/security data, profiles,
  entitlements, and every unrelated library.
- Allow only Owners to create a full portable export.

### 8E — Server restore and acceptance gate

- Restore a Server-portable ZIP through the same quarantine, report, quota,
  duplicate-decision, staging, and atomic-consolidation guarantees.
- Add the Owner-facing Data & portability UI and progress/error recovery.
- Repeatedly import anonymized real Local-v8 fixtures and restore Server
  exports into fresh libraries.
- Prove preserved counts/values and prove that every induced failure leaves no
  database rows, charged bytes, or private objects behind.

## Non-goals

- Never replace PostgreSQL with an uploaded SQLite file.
- Never import account credentials or infer a reading Owner.
- Never retain raw uploads indefinitely.
- Never silently merge duplicate physical copies.
- Production-wide PostgreSQL disaster recovery remains Phase 9 operations,
  separate from user-facing library portability.
