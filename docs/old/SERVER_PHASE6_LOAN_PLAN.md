# BOOKPILE Server Phase 6 — shared loans and private borrower data

Status: complete on `feature/server-loans`, awaiting explicit approval to merge.
Phases 6A–6D were completed and manually accepted on 2026-09-08; 6E passed its
compatibility and release gates the same day. Phase 6 changes Server only; released
BOOKPILE Local v1 and its populated SQLite catalogue remain untouched.

## 1. Objective and ownership boundary

A loan describes the temporary custody of one physical copy. It belongs to the
shared library, not to one Owner's reading perspective. Every Owner may create,
return, correct, or delete a loan record. Viewers may see that the copy is
unavailable and may inspect non-sensitive dates, but must never receive the
borrower's free-text identity or private loan notes.

Loans do not replace personal reading states. A copy can remain `Pending`,
`Reading...`, `Re-reading...`, or `Read` for each Owner while its shared custody
is `ON_LOAN`. A current loan takes visual priority over the Reading area, but an
already-active reading remains active in counters and statistics.

## 2. Agreed behaviour

- One physical book may have at most one active loan.
- `loaned_to` is required free text, normalized for surrounding/repeated
  whitespace, with a 300-character limit. It is not linked to a BOOKPILE user.
- Private notes are optional free text with a 4,000-character limit.
- The loan date may be known or explicitly unknown.
- Expected return is optional and may be in the future.
- A returned loan may have a known or explicitly unknown return date.
- Known loan and return dates cannot be in the future. When both relevant
  dates are known, expected return and actual return cannot precede the loan.
- Normal Return proposes today's date. Historical records may use unknown
  dates. Unknown-date records sort before dated history; ties use record
  creation order.
- Historical returned loans may be added, edited, and deleted. The active loan
  is created through Loan book, completed through Return book, or removed
  through an explicitly confirmed cancellation; history editing must not
  silently create a current loan.
- Single Add and Batch Add may create a book already on loan. Batch Add clears
  loan values before the next book.
- Starting a new reading or rereading while a copy is on loan is rejected.
  Loaning an already-being-read copy is allowed; returning it reveals the
  Reading area again if the session remains active.
- Reading suggestions exclude copies on loan.
- Deleting a book always requires the existing explicit confirmation and also
  removes its loan history through the reviewed cascade.

## 3. Canonical Server data model

Add a `loans` table through one additive Alembic migration:

```text
id                    UUID primary key
library_id            UUID not null
book_id               UUID not null
state                 ACTIVE | RETURNED
loaned_to             varchar(300) not null
notes                 varchar/text(4000) nullable
loaned_date           date nullable
expected_return_date  date nullable
returned_date         date nullable
created_at            timestamptz not null
updated_at            timestamptz not null
```

Use a composite foreign key `(library_id, book_id) -> books(library_id, id)` so
a loan cannot cross library boundaries. Use `ON DELETE CASCADE` only because
book deletion already requires an explicit user confirmation. Add:

- a partial unique index on `(library_id, book_id) WHERE state = 'ACTIVE'`;
- state and nonblank borrower checks;
- chronology checks for every pair of known dates;
- indexes for library/book history, active expected-return queries, borrower
  lookup, and returned-date sorting.

`created_at` is the stable tie-breaker for unknown histories. Actor identity
belongs in the existing immutable library audit event, not in the shared loan
record. Audit details contain IDs, state transitions, and dates only—never
borrower text or private notes.

Shared custody remains a projection:

```text
active loan exists  -> ON_LOAN
else active reading -> BEING_READ
else                 -> SHELVED
```

It is not stored as a second mutable book status.

## 4. Privacy and API projections

Do not serialize one universal Loan object and hide fields in React. Define
separate response schemas at the backend boundary:

- Owner projection: full borrower, notes, state, and dates.
- Viewer projection: state and non-sensitive dates only; no borrower or notes
  keys at all.
- Catalogue-only Viewer: availability is visible, but retained physical
  location and all map data remain absent under the existing scope rules.
- Outsider or wrong-library UUID: existing not-found isolation applies.

Borrower search is Owner-only. A Viewer request that attempts a borrower
filter must be rejected rather than silently interpreted differently. Viewer
statistics may include aggregate active, overdue, returned, and by-year counts,
but never group or label results by borrower. Error messages, audit records,
logs, traces, and validation responses must not echo private free text.

Proposed route family:

```text
GET    /libraries/{library}/catalogue/{book}/loans
POST   /libraries/{library}/catalogue/{book}/loans/active
POST   /libraries/{library}/catalogue/{book}/loans/active/return
DELETE /libraries/{library}/catalogue/{book}/loans/active
POST   /libraries/{library}/catalogue/{book}/loans/history
PUT    /libraries/{library}/catalogue/{book}/loans/{loan}
DELETE /libraries/{library}/catalogue/{book}/loans/{loan}
```

All writes require Owner membership, CSRF, row locking, validation, and a
library audit event. Updates are complete replacements rather than ambiguous
partial patches.

## 5. Concurrency and transaction rules

Starting/returning/cancelling a loan and starting a reading lock the same Book
row before checking custody. This serializes competing co-Owner actions:

- two simultaneous loans: exactly one succeeds;
- simultaneous new reading and active loan: the operation that establishes the
  loan first causes the reading to fail; a pre-existing reading does not block
  a later loan;
- return versus cancellation/edit: stale second operation fails clearly;
- all book-plus-initial-loan creation is atomic except the already-separated
  cover upload, whose partial-success UX remains unchanged.

The partial unique index is the final database barrier, not the sole business
rule. Repository methods must always scope by both `library_id` and `book_id`.

## 6. Migration safety protocol

Before schema work:

1. Confirm branch, clean worktree, current commit, Alembic head, and table/count
   baseline.
2. Create a timestamped custom-format PostgreSQL backup and verify its listing.
3. Restore it into a uniquely named disposable database and verify books,
   contributors, covers, hierarchy, layouts, memberships, personal records,
   and reading sessions.
4. Add one reversible, additive migration. Do not reinterpret existing data.
5. Rehearse upgrade, invariants, downgrade, and second upgrade on the restored
   database before migrating development.
6. Apply to development only after all automated gates pass; verify identical
   pre-existing counts and values afterward.
7. Keep the backup until Phase 6 is accepted and merged.

Downgrade is permitted only when `loans` is empty. If loan rows exist, fail
with an explanation instead of deleting history. This makes rollback during
the empty-schema increment safe and prevents accidental destructive rollback
after user testing.

## 7. Implementation increments

### 6A — schema and pure loan domain

Status: complete on the feature branch. Migration `0014_shared_loans`, the
`Loan` model, canonical pure rules, SQLite tests, and the PostgreSQL migration
gate are implemented. The verified pre-migration backup is retained at
`server/backups/bookpile-phase6a-pre-20260908-064317.dump`. Its restoration in
an isolated database preserved all 15 development books; development now runs
at `0014_shared_loans` with an empty loan table.

- Add `Loan`, constraints, indexes, relationships, and migration.
- Implement normalization, chronology, overdue, sorting, and custody helpers as
  pure functions.
- Add SQLite/unit schema tests plus the real PostgreSQL migration rehearsal.
- Prove that all Phase 5 records remain unchanged.

Gate: backup/restore and upgrade/downgrade/upgrade pass; race barriers and date
edge cases have automated coverage. No frontend yet.

Estimated effort: 20–30% of one full coding context.

### 6B — scoped repositories, services, and APIs

Status: complete on the feature branch. Owner and Viewer responses are
different schemas; Viewer payloads contain no borrower or private-note field.
The shared lifecycle, catalogue overview, book history, CSRF, tenant scope,
Book-row locking, reading-start exclusion, concurrent-Owner race, and redacted
audit events pass the full 115-test Server suite, including PostgreSQL.

- Add library-scoped history and active-loan repository queries.
- Add start, return, cancel, historical create/update/delete services.
- Lock the Book row and integrate the on-loan check into reading start.
- Add Owner and Viewer response projections and audit events.
- Extend catalogue/complete-information responses with safe availability and
  loan summaries.
- Test two Owners, both Viewer scopes, outsider access, cross-library IDs,
  CSRF, borrower-filter privacy, and concurrent writes.

Gate: API tests prove no Viewer response or error can recover borrower or note
data and no cross-library operation succeeds.

Estimated effort: 25–35%.

### 6C — catalogue actions, Add, and history UX

Status: complete and accepted. The responsive catalogue exposes Owner loan
management, Viewer-redacted availability, atomic initial placement plus loan,
Single/Batch Add, complete-information history, filters and date sorting.

- Add a Loan/Return button beside Complete information, Goodreads, Edit, and
  Delete. It changes label and icon according to active custody.
- Owners see `On loan: <borrower>`; Viewers see only `On loan`, with the
  unavailable icon and no sensitive tooltip/accessibility text.
- Keep complete information read-only. Owners manage loan history inside Edit
  book, matching the accepted reading-history separation.
- Add current-loan fields to Single Add and each Batch Add item; clear them
  between batch records.
- Add current, overdue, ever-loaned, never-loaned, history-scope, date, and
  Owner-only borrower filters; add loan/expected/returned date sorting.
- Add concise destructive confirmations for cancel, history deletion, and book
  deletion with loan history.

Gate: desktop and phone Owner/Viewer acceptance, including a newly created book
that begins on loan.

Estimated effort: 30–40%.

### 6D — map, suggestions, and statistics

Status: complete and accepted. Shared active custody populates the On-loan
area with priority over Reading, retained positions survive, inspection is
privacy-safe, suggestions exclude loans, and shared loan statistics coexist
with perspective-specific reading statistics.

- Populate the existing On-loan outside area from shared active loans, taking
  priority over Reading without losing retained shelf positions or sessions.
- Make loaned visual books inspectable; redact borrower/notes for Viewers.
- Return a copy to Reading or its shelf projection when the loan ends.
- Exclude active loans from every suggestion path.
- Add active, overdue, completed, unknown-date, known-loans-by-year, and
  most-loaned-book statistics under existing metadata filters.
- Add map/filter regression tests for selected reading perspectives: custody is
  shared even though reading colour remains personal.

Gate: accepted on desktop and phone for Owner and Viewer, including a book that
is simultaneously being read and on loan.

Estimated effort: 25–35%.

### 6E — compatibility, documentation, and final acceptance

Status: complete; branch is ready for the guarded merge. The Local contract
comparison, privacy review, 116-test backend suite, 23 frontend tests, lint,
production Server build and opt-in PostgreSQL gate all pass. No Local source or
populated data was modified.

- Compare Server behaviour against the accepted Local loan contract without
  copying Local's single-user architecture.
- Run the complete backend, opt-in PostgreSQL, frontend, lint, build,
  authorization, responsive, and concurrency gates.
- Update README, TODO, cross-edition mapping, operator notes, and progress.
- Commit/push only accepted increments; merge Phase 6 only after explicit user
  approval.

Gate: Phase 6 supplies the canonical loan destination required before Phase 8
Local ZIP import can begin. Backups/exports themselves remain Phase 8.

Estimated effort: 10–20%.

### Local-to-Server compatibility result

Both editions now agree on required borrower text, optional notes and dates,
chronology, one active loan per copy, retained shelf position, reading/loan
independence, custody priority, history, search, map and statistics semantics.
Server deliberately replaces Local's implicit single-user trust boundary with
library-scoped UUIDs, Book-row locking, CSRF, immutable redacted audit events,
Owner writes and structurally separate Viewer responses. These are hosted-mode
security requirements, not data incompatibilities. Consequently Local v1 loan
rows have a canonical lossless destination for the Phase 8 ZIP adapter.

## 8. Acceptance matrix

Automated and manual validation must cover:

- active loan with known and unknown loan date;
- optional expected return and overdue boundary using the Server timezone/date;
- returned history with known and unknown return date;
- impossible chronology and future-date rejection;
- one-active-loan enforcement under concurrent Owners;
- simultaneous reading/loan transaction ordering;
- Loan, Return, Cancel, history edit/delete, Single Add, and Batch Add;
- catalogue, complete information, advanced filters, sorting, map,
  suggestions, and statistics;
- return to Reading versus return to shelf while retaining physical position;
- Owner full projection; Viewer redacted projection; catalogue-only map denial;
- borrower/note absence from JSON, logs, audit details, errors, tooltips, and
  accessible labels;
- outsider, stale membership, and cross-library UUID denial;
- migration preservation and non-destructive downgrade guard;
- desktop and mobile layout and interaction.

## 9. Explicitly deferred work

- Server backup/export/restore and Local ZIP conversion: Phase 8, now unblocked
  only after Phase 6 is complete.
- Storage accounting and shared co-Owner quota: Phase 7.
- Linking borrowers to BOOKPILE accounts, reminders, notifications, or email.
- Public loan activity or borrower disclosure.
- Physical-move history.

## 10. Recommended next session

After explicit approval, merge `feature/server-loans` into `main`, verify the
merge commit and remote branch, and retain the Phase 6 pre-migration backup.
Then create a fresh Phase 7 branch; do not mix quota/deletion work into this one.
