# BOOKPILE cross-edition data model

Status: Phase 3.5 design baseline

Date: 2026-08-31

Scope: BOOKPILE Local after v1.0.0 and BOOKPILE Server Phase 4 onward

## 1. Purpose

BOOKPILE Local and BOOKPILE Server serve the same library domain but do not
have identical storage requirements. Local has one implicit library and one
implicit reader. Server can have several libraries, equal co-Owners, scoped
Viewers, and a different reading history for every Owner.

This document defines a shared **semantic model**. It is deliberately not a
promise that SQLite and PostgreSQL will use identical tables or identifiers.
It prevents Server from copying Local's single-user assumptions and prevents
future Local additions from forcing a redesign of Server.

The stable Local v1.0.0 release and its schema-v8 ZIPs remain supported source
formats. No database is changed merely by accepting this document.

## 2. Decisions and invariants

1. A BOOKPILE `book` continues to mean one owned physical copy. BOOKPILE will
   not introduce Work/Edition/Copy normalization in this phase.
2. Bibliographic and physical-copy metadata are shared by the members of the
   library that owns the copy.
3. Reading sessions, reading status, rereads, reading statistics, and future
   personal ratings belong to an individual Owner.
4. Physical location and custody belong to the shared library.
5. Loans belong to the shared copy, but borrower identity and private loan
   notes are returned only to Owners.
6. Viewers can read only the projection allowed by their membership scope.
   Catalogue-only Viewers never receive data from which the physical map or
   retained shelf position can be reconstructed.
7. Local numeric IDs are source identifiers only. Server creates UUIDs and
   records an import mapping; it never treats a Local ID as globally unique.
8. Optional future fields are additive and nullable. Absence means unknown,
   not zero, empty, original-language, or any other inferred fact.
9. The original free-text `author` value remains preserved for compatibility
   and display. Structured contributors supplement it rather than destroying
   it.
10. Import is a validated conversion into a selected library, not a database
    restore and not a table-for-table copy.

## 3. Data ownership classes

### 3.1 Platform identity and security

These records exist only in Server and never belong in a Local ZIP:

- User accounts, normalized email addresses, usernames, and password hashes.
- Sessions, CSRF state, verification and recovery tokens.
- Account invitations, rate-limit buckets, and security events.
- Platform-administration state.

They are account-scoped or platform-scoped and must never be exported through
a library backup.

### 3.2 Shared library data

All Owners share and maintain these records. Viewers receive an authorized
read-only projection:

- Library identity and display settings.
- Physical book copies and bibliographic metadata.
- Ordered contributors and their roles.
- Bookcases, shelves, containers, book positions, and visual layout.
- Covers, subject to authenticated private delivery.
- Acquisition information, shared notes, and copy dimensions.
- Shared physical custody: shelved, being read, or on loan.
- Loan records. Borrower identity and loan notes remain Owner-only.
- Future structured genres and subjects.

### 3.3 Personal Owner data

These records are attached to both a library book and an Owner:

- Reading sessions, active reading, rereading, and historical unknown reading.
- Per-Owner reading-status projections and statistics.
- Each Owner's Goodreads review URL for a library book. Owners may edit only
  their own link; all Owners and authorized Viewers may read every recorded
  review, labelled with the reviewer's visible username.
- The Owner currently holding/reading a physical copy where custody requires
  it.
- Future personal ratings and personal tags.
- Future personal recommendations or hidden/saved suggestion state.

Other Owners and authorized Viewers may inspect reading information read-only
under the agreed privacy policy, but cannot modify it.

### 3.4 Presentation and device state

These values are not catalogue facts:

- Current map camera, zoom, collapsed panels, and selected colour mode.
- Open inspector and temporary selection.
- Unsaved rearrangement drafts.
- Current search/filter form.
- Batch Add's selected import-field subset for the current session.

Device-local presentation state should normally use browser storage. A future
cross-device preference may be stored per user, but never as book metadata.

### 3.5 Transient external evidence

These values exist during scanning and do not become authoritative merely
because a provider returned them:

- Raw provider responses and per-field provenance.
- Candidate confidence and conflicts.
- Temporary barcode/OCR photographs.
- Late provider responses received after the user has submitted or cancelled.

Only fields explicitly reviewed and accepted by the user enter the catalogue.

## 4. Canonical catalogue model

The names below describe concepts. Exact SQL names and constraints are chosen
in each edition's reviewed migration.

### 4.1 Library

Server libraries have a UUID, name, slug, lifecycle state, timestamps, and
memberships. Local has one implicit library and therefore does not need a
library row solely to imitate Server.

### 4.2 Physical book copy

One record represents one physical copy and includes:

- Required title and legacy Author display text.
- ISBN-10 and ISBN-13; duplicates remain valid for intentionally duplicated
  copies.
- Subtitle, page count, publisher, current-edition year, original publication
  year, edition number, series name, and series volume.
- Edition language, original language, and translation status.
- Fiction category, binding, publication type, and interim genre text.
- Shared notes, acquisition data, cover reference, timestamps, and physical
  position.
- Optional physical dimensions.

The current Local `status`, `reading_started_date`, `read_date`, and
`is_read_date_unknown` columns are compatibility projections of the implicit
Local reader. They must not become shared columns with the same meaning in
Server. Server derives the corresponding view from the selected Owner's
reading sessions.

Local's current Goodreads URL is the implicit Local user's personal review,
not shared bibliography. Server import assigns it to the Owner selected for
the imported Local user. The dormant Phase 4A `books.goodreads_url` column is
not exposed by Phase 4B and will be retired through a backed-up migration when
the personal Owner/book relation is introduced in Phase 5.

### 4.3 Ordered contributors

Contributors generalize the existing structured-author relationship:

```text
Book contributor
├── book
├── role
├── display order within that role
└── credited name
```

Initial controlled roles:

- `AUTHOR`
- `SCRIPTWRITER`
- `TRANSLATOR`
- `ILLUSTRATOR`
- `PENCILLER`
- `INKER`
- `COLORIST`
- `LETTERER`
- `COVER_ARTIST`
- `EDITOR`
- `COORDINATOR`
- `COMPILER`
- `PHOTOGRAPHER`
- `ADAPTER`
- `OTHER`

`AUTHOR` remains the general written-work credit. `SCRIPTWRITER` can preserve
a more specific comic, graphic-novel, theatre, or screenplay credit when the
source edition makes that distinction. Comic credits can separately represent
pencils, inks, colour, lettering, illustration, and cover art. `COORDINATOR`
and `COMPILER` cover collective works without pretending that coordination is
authorship.

Roles form a controlled but extensible vocabulary. They should use stable text
codes referenced through a small role-definition table, not a rigid
PostgreSQL native enum or a destructive table constraint. Adding a future role
such as cartographer or researcher then requires an additive role definition
and application support, not rewriting contributor records or invalidating
old backups. A role code already used by a book is never deleted; it may later
be marked inactive for new selection while remaining displayable.

Rules:

- Names are required, trimmed, order-preserving, and unique within one book
  and role after normalized comparison.
- Several people may have the same role.
- The same person may appear under different roles when genuinely credited in
  both capacities.
- A free-text Author value remains required for compatibility. Existing Local
  values are not rewritten by import.
- Local `book_authors` rows become `AUTHOR` contributors in their saved order.
- Provider contributors are suggestions. A provider label such as translator,
  editor, or illustrator must never be silently imported as an author.

A future contributor identity/deduplication system is explicitly out of scope:
names remain credited strings, not global people profiles.

### 4.4 Language and translation

The current Local `language` means **the language of this edition** and is
preserved with that meaning.

The common model adds:

- `original_language`: optional free-text original language.
- `translation_status`: controlled `UNKNOWN`, `ORIGINAL`, or `TRANSLATED`.
- Zero or more ordered `TRANSLATOR` contributors.

The status is not inferred solely by comparing two strings. Missing language,
alternative names, regional variants, and multilingual originals make such an
inference unreliable. A translated edition may temporarily have no known
translator; that is incomplete metadata, not an invalid record.

Normalization and eventual localized controlled vocabularies remain later
work. Current values must be preserved losslessly.

### 4.5 Physical dimensions

Dimensions are optional measurements, stored internally as positive integer
millimetres. The UI may accept centimetres and convert them without storing
binary floating-point measurements.

For a physical book copy:

- `height_mm`
- `width_mm` — front-cover width
- `thickness_mm` — spine thickness

Each value is independently nullable because a user may initially measure
only the useful dimension. Zero means invalid; unknown is `NULL`.

For a bookcase/furniture item:

- Outer `height_mm`
- Outer `width_mm`
- Outer `depth_mm`

For a shelf:

- Usable inner `height_mm`
- Usable inner `width_mm`
- Usable inner `depth_mm`

Rows and piles are logical arrangements rather than necessarily physical
objects, so containers do not receive arbitrary measured dimensions in the
baseline. Their occupied size is derived from their books, shelf limits,
orientation, and layout rules.

Map consequences are now specified normatively in
`PHYSICAL_GEOMETRY_PLAN.md`. In summary:

- A row uses book thickness along its stacking axis and book height on its
  vertical axis.
- A pile uses thickness vertically and cover width horizontally.
- Furniture and shelves can use measured aspect ratios where enough data is
  present.
- There is one canonical geometry with shared `MANUAL` and `PHYSICAL` modes,
  not two competing layouts. Percentage container placement remains useful;
  physical mode recalculates those same values from measurements and fallbacks.
- When a measurement is absent, the current page-count, catalogue-mean, and
  fixed-fallback hierarchy remains available.
- Server implements this model first. A later Local release may backport it
  only through isolated acceptance data and a rehearsed additive migration.

Exact plausibility ranges and mixed measured/estimated calibration must be
validated with real data before implementation. They are not silently fixed by
this document.

## 5. Physical hierarchy and layout

The shared hierarchy remains:

```text
Library → Bookcase → Shelf → Container → Positioned book copy
```

- Every Server hierarchy row carries a `library_id` directly or has an
  unambiguous library path enforced by foreign keys.
- A book may retain a container and position while custody displays it in the
  Reading or On-loan area.
- Bookcase, shelf, container, world-coordinate, shelf-weight, row-anchor, pile
  support, and outside-area layout values are shared library data.
- Catalogue-only responses omit this hierarchy and derived location labels.
- Measured dimensions never replace collision, support, or containment
  validation.
- Physical mode uses an unbounded millimetre world with furniture `x` and
  `floor_y`; container dimensions are derived from books and shelf interiors.
  Physical violations are derived diagnostics and do not silently discard
  truthful metadata.

## 6. Readings and custody

### 6.1 Local source meaning

Local `reading_sessions` belong to its one implicit user. Its legacy book
status/date fields mirror the active or latest session.

### 6.2 Server meaning

Every Server reading session must include `user_id`, `library_id`, and
`book_id`, with the Owner/member relationship validated. Status is calculated
for the selected reading perspective.

During Local ZIP import, the user must select one Owner to receive all Local
reading sessions. Import must not assign them to every co-Owner.

Shared custody is related but distinct:

- `SHELVED`: physically available at the retained location.
- `BEING_READ`: temporarily held by one Owner; personal sessions determine
  whose reading is active.
- `ON_LOAN`: absent under the shared loan workflow.

The rules for one active physical reader and loan conflicts are implemented in
Phase 5 onward, not in Phase 4 catalogue storage.

## 7. Loans and sensitive projections

Local loans map to shared Server loan records for the imported physical copy.
Known/unknown dates, history, state, expected return, and timestamps are
preserved.

API projection rules:

- Owners may view and manage borrower identity and loan notes.
- Viewers may see availability/On-loan state where useful, but never
  `loaned_to` or private loan notes.
- Catalogue-only Viewers receive no retained physical position.
- Library export is Owner-only.

## 8. Current Local-v8 to Server mapping

| Local source | Server destination | Classification | Conversion rule |
| --- | --- | --- | --- |
| Implicit installation | Selected `library` | Shared | User selects or creates destination |
| `bookcases` | Library bookcases | Shared/map-sensitive | Generate UUIDs; retain names/descriptions |
| `shelves` | Library shelves | Shared/map-sensitive | Map through imported bookcase IDs |
| `containers` | Library containers | Shared/map-sensitive | Preserve type, layer, number, and shelf |
| `books` bibliographic fields | Physical book copies | Shared | Preserve values; generate UUIDs |
| `books.container_id/position` | Copy placement | Shared/map-sensitive | Map through imported container IDs |
| `book_authors` | Contributors with `AUTHOR` role | Shared | Preserve order and credited spelling |
| Legacy Author text | Book Author display text | Shared | Preserve exactly; do not regenerate |
| `reading_sessions` | Owner reading sessions | Personal | Assign to the explicitly selected Owner |
| Legacy reading projections | Import validation inputs | Personal projection | Reconcile with sessions; do not make shared status |
| `loans` | Shared loan history | Owner-sensitive | Preserve; redact borrower data from Viewers |
| Cover files | Private library cover objects | Shared/private | Validate, transform/store privately, map reference |
| `visual_layout_items` | Library world layout | Shared/map-sensitive | Preserve finite coordinates and dimensions |
| `visual_shelf_layout` | Shelf presentation | Shared/map-sensitive | Preserve height weights |
| `visual_container_layout` | Container presentation | Shared/map-sensitive | Preserve geometry, anchor, and pile support |
| Local IDs | Import mapping only | Operational | Never expose as Server identity |

Fields introduced in a future Local schema map into the same semantic model;
they do not require changing the meaning of these existing mappings.

## 9. Versioned Local ZIP import contract

### 9.1 Source version identification

The current ZIP identifies:

- `format = BOOKPILE_BACKUP`
- `backup_format_version = 1`
- Local `schema_version` (currently up to 8)
- Counts, checksums, creation time, database, and cover files

Backup format and database schema are independent versions. Adding nullable
database fields normally increments `schema_version`; changing ZIP structure
or manifest semantics increments `backup_format_version`.

### 9.2 Adapter registry

Server selects an importer by the pair:

```text
(backup_format_version, local_schema_version)
```

An adapter reads a documented source version and emits canonical import
records. It does not issue Server SQL directly.

Older supported archives remain valid. A newer unknown format/schema is
rejected with an explanatory report rather than guessed. Support can be added
by a new adapter without changing earlier adapters.

### 9.3 Safe pipeline

1. Receive the ZIP into isolated temporary/quarantine storage with strict size
   and path limits.
2. Verify archive paths, manifest shape, checksums, counts, SQLite integrity,
   foreign keys, and referenced covers.
3. Identify the exact source adapter.
4. Read or migrate only a disposable extracted copy when an internal Local
   migration is required; never alter the uploaded archive.
5. Convert source rows into canonical records and produce a preflight report.
6. Ask the Owner to select destination library and reading-history Owner.
7. Check authorization, conflicts, duplicate policy, and future storage quota.
8. Insert into staging or one database transaction while building explicit
   source-ID-to-UUID mappings.
9. Process covers through the private image pipeline; a failed cover cannot
   leave a half-imported visible library.
10. Validate post-import counts, relationships, permissions, and canonical
    fingerprints.
11. Consolidate atomically or roll back everything.
12. Retain a non-sensitive import report and audit event; delete temporary raw
    files according to the retention policy.

An import job records source manifest fingerprint and destination. Repeating
the same ZIP must be detected and require an explicit user decision, rather
than silently duplicating every book.

### 9.4 Import report

Before consolidation, report at least:

- Source versions and creation date.
- Counts for books, hierarchy, contributors, readings, loans, and covers.
- Destination library and selected reading Owner.
- Unsupported or incomplete fields.
- Duplicate ISBN/title candidates as warnings, not automatic rejection.
- Missing/invalid covers and any sanitized files.
- Estimated storage charge when quotas are enabled.
- Fatal relationship, integrity, permission, or capacity errors.

## 10. Progressive multi-source ISBN lookup

Multi-source scanning shares the canonical candidate shape but is not a
database-import operation.

Responsiveness requirements:

1. Normalize the ISBN and check the current catalogue immediately.
2. Start provider requests concurrently on the backend.
3. Return each provider's usable result as soon as it arrives; do not wait for
   the slowest provider before showing the first candidate.
4. Use short provider-specific connection and total timeouts, cancellation,
   and a bounded overall lookup lifetime.
5. Merge fields progressively while retaining provider provenance and visible
   conflicts.
6. Never replace a field the user has typed, edited, deselected, or explicitly
   accepted merely because a later provider answered.
7. If the user saves or cancels, late responses are ignored and outstanding
   work is cancelled where practical.
8. Keep provider credentials and provider-specific payloads on the backend.
9. Cache safe ISBN results for a bounded period to reduce latency and provider
   load, while still allowing a refresh.

Server-Sent Events or a streamed response is preferred for one-way progressive
updates; WebSockets are unnecessary unless future live scanning requires
two-way continuous communication. The final transport will be selected after
a small latency and browser-reliability prototype.

Every field shows its source and remains reviewable. Several explicit authors
initialize ordered `AUTHOR` contributors. Explicit translators,
illustrators, editors, and photographers initialize their own roles and are
never folded into Author. Ambiguous unlabeled names remain unselected.

During Batch Add, the accepted-field mask is copied to the next item for that
session only. It controls initial selection, not silent saving, and is cleared
when the batch ends unless a later per-user preference is explicitly designed.

## 11. Evolution strategy

### Local

- The published v1.0.0 tag and release artefacts remain immutable. This means
  the distributed historical release is reproducible; it does not prohibit a
  later Local v1.1 or an explicitly approved upgrade of the owner's live app.
- `C:\Users\Russula\.code\_PERSONAL_LIBRARY_MANAGER` remains the usable live
  personal library. Development and migration rehearsals must not use its
  database as a test target.
- Future Local features use a separate branch and worktree, with its own data
  directory. Realistic acceptance data is introduced by creating a validated
  full ZIP from the live app and restoring that ZIP into the isolated test
  worktree. The live data directory is never copied opportunistically while
  BOOKPILE is running.
- An additive Local schema migration is rehearsed against that disposable
  restored copy. Updating the live installation happens only after explicit
  approval, a new verified backup, successful rehearsal, and acceptance of
  the new Local version.
- Existing ZIPs remain restorable by compatible Local versions and importable
  by Server adapters.

### Server

- Each migration is reversible where practical and rehearsed against
  disposable PostgreSQL.
- Every library-level relation is scoped and authorization-tested.
- Shared and personal records are not collapsed for convenience.
- New Local fields extend an adapter and canonical mapping; they do not require
  mirroring Local's SQLite schema.

### Shared specifications, separate persistence

Validation vocabulary, canonical candidate structures, and import fixtures may
eventually be shared. Database models and migrations remain edition-specific.
Prematurely forcing both applications to import the same persistence package
would couple stable Local operation to hosted deployment concerns.

## 12. Phase 4 implementation slices

Phase 4 should proceed in reviewable increments:

1. **4A — shared catalogue schema (completed):** expand Server books, contributors,
   language/translation, optional dimensions, hierarchy, and layout with
   library scoping and migration tests.
2. **4B — catalogue services (completed):** port create/edit/search/filter
   behavior, complete replacement updates, ordered contributors, normalized
   shared metadata, and Owner-write versus Viewer-read authorization.
3. **4C — private covers:** authenticated storage/delivery, strict image
   validation, non-public object identifiers, abuse limits, and isolation
   tests.
4. **4D — physical hierarchy and map reads:** port layout data and provide
   catalogue-only versus catalogue-and-map serialization tests.
5. **4E — importer groundwork:** implement manifest validation, canonical
   adapters, dry-run reports, and fixtures without importing the live personal
   library yet.

Personal readings, shared custody, loans, quotas, and production deployment
continue in their already defined later phases.

## 13. Phase 3.5 exit criteria

Phase 3.5 is complete when:

- The ownership classes and Local-v8 mapping are reviewed.
- Contributors, languages, dimensions, and progressive lookup behavior have a
  stable semantic definition.
- ZIP versioning and the safe adapter pipeline are accepted.
- No Local or Server database has been altered.
- Phase 4 can design PostgreSQL tables from this model without copying Local's
  single-user reading projections.
