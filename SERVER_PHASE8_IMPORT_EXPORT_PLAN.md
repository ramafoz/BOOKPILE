# BOOKPILE Server Phase 8 — Import, export, and recovery

## Objective

Phase 8 makes one library portable without treating a Local SQLite database as
a Server database. A validated Local v1 ZIP is converted into canonical
records and then consolidated into one selected Server library. Server exports
contain only that library and its permitted member-owned data; they never
contain credentials, sessions, account profiles, or unrelated libraries.

## Delivery slices

### 8A — Local ZIP inspection and adapter foundation (completed 2026-09-09)

- Enforce a 100 MiB compressed upload limit, bounded entry count, bounded
  expanded size, suspicious compression-ratio checks, safe paths, and no
  encrypted entries or links.
- Validate the manifest, exact file list, sizes, SHA-256 checksums, SQLite
  integrity and foreign keys, record counts, referenced covers, and WebP image
  contents in isolated temporary storage.
- Select the source adapter by `(backup_format_version, schema_version)`.
- Support the published Local backup format 1 / schema 8 first and emit a
  deterministic, non-sensitive preflight report without writing Server data.

### 8B — Authenticated preflight jobs (completed and accepted 2026-09-09)

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

### 8C — Atomic Local-to-Server consolidation (completed and accepted 2026-09-09)

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

### 8D — Server-portable library export (completed and accepted 2026-09-09)

- Define a versioned canonical Server ZIP with manifest and checksums.
- Export one selected library, its physical/map data, cover objects, loans,
  and personal reading/review records labelled by stable member references.
- Exclude passwords, tokens, sessions, email/security data, profiles,
  entitlements, and every unrelated library.
- Allow only Owners to create a full portable export.

The Owner-facing `Data & portability` workspace is also implemented. It can
download this export and run the Local preflight/consolidation flow without
exposing either operation to Viewers.

The accepted Local-import experience provides visible long-operation feedback,
source counts, warning review, cancellation with staging erasure, import into
the selected library, and atomic creation/import of a separate new library.
The importing user is the new library's first Owner and receives the implicit
Local personal history; no membership is inferred. A failure rolls back both
the new library and all imported records and objects.

Acceptance with a substantially larger real Local catalogue also exposed and
closed two general presentation issues: unmeasured physical shelves divide the
available furniture span equally and retain optional visual overrides, while
containers whose books have no explicit measurements retain an editable visual
envelope. An unmeasured row can explicitly fill its complete shelf; once any
book measurement exists, truthful physical projection governs again. Long book
tables in statistics show approximately ten rows with their own scrollbar.

### 8E — Server restore and acceptance gate

- Restore a Server-portable ZIP through the same quarantine, report, quota,
  duplicate-decision, staging, and atomic-consolidation guarantees.
- Extend the existing Owner-facing Data & portability UI with Server restore,
  member mapping, progress, and recoverable errors.
- Repeatedly import anonymized real Local-v8 fixtures and restore Server
  exports into fresh libraries.
- Prove preserved counts/values and prove that every induced failure leaves no
  database rows, charged bytes, or private objects behind.

Before restore is implemented, define how each exported stable member key is
mapped to a current destination Owner. The shared catalogue may be restored
independently, but personal readings and Goodreads links must never be assigned
implicitly and restoring an archive must never grant library membership.

## Non-goals

- Never replace PostgreSQL with an uploaded SQLite file.
- Never import account credentials or infer a reading Owner.
- Never retain raw uploads indefinitely.
- Never silently merge duplicate physical copies.
- Production-wide PostgreSQL disaster recovery remains Phase 9 operations,
  separate from user-facing library portability.
