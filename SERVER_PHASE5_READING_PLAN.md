# BOOKPILE Server Phase 5 — personal readings and shared custody

Status: 5A complete and 5B implemented and automatically verified on the Server
feature branch; 5C is the next user-visible increment. This phase changes
Server only. Released BOOKPILE Local v1 and its populated SQLite database remain
untouched.

## 1. Objective and boundary

Phase 5 separates three concepts that Local can safely treat as one because it
has one user:

- the **book copy and catalogue metadata**, shared by the library;
- the **reading history and Goodreads review**, personal to each Owner;
- the **physical custody of the copy**, shared because there is only one
  physical object.

This phase does not implement loans, Local ZIP import, storage quotas, payment,
public profiles, or production deployment. Loans are Phase 6. Full Local ZIP
import remains blocked until both Phase 5 and Phase 6 have canonical targets.

## 2. Agreed behaviour

- Reading sessions belong to one Owner, one library, and one book.
- Owners may select their own or another Owner's reading perspective. Viewers
  may inspect the permitted Owners' dates, histories, and statistics but never
  write them.
- An Owner may change reading data only while viewing their own perspective.
- Personal display states are `Pending`, `Reading...`, `Re-Reading...`, and
  `Read`. Re-reading does not increase the unique-book hero total.
- Shared custody is `SHELVED`, `BEING_READ`, or later `ON_LOAN`. Phase 5
  implements the first two; Phase 6 completes loans.
- A physical copy can have at most one active reader, even when the library has
  several co-Owners.
- Starting a reading requires a known start date. Cancelling a first reading
  returns that Owner to `Pending`; cancelling a rereading returns them to
  `Read`.
- Completed known sessions require both start and finish dates. Unknown dates
  mean both are unknown, are historical only, and never represent an active
  reading.
- At most one unknown historical session is allowed per Owner and book. It is
  ordered before all known sessions.
- Known sessions for the same Owner and book cannot overlap. A new session may
  begin on the day a previous one finishes, but duplicate indistinguishable
  same-day sessions are rejected.
- Reading history is chronological. Deleting an intermediate session
  renumbers presentation order. Destructive edits and deletes require an
  explicit warning; deleting the sole session returns the personal state to
  `Pending`.
- Rereads count as reading events and add pages to time-based statistics.
  Headline `Books read` remains a unique-book count. Inclusive duration is
  used: same-day reading is one day.
- Missing page count excludes page-derived metrics. Editing shared page count
  immediately changes derived statistics but never rewrites a session.
- Acquisition history remains shared copy metadata.
- Goodreads review URLs are personal to an Owner. Owners edit only their own;
  authenticated library members may read all reviews, labelled by visible
  username. The existing dormant shared column is retained until data
  preflight proves it can be retired safely.
- Perspective drives personal catalogue state, history, statistics,
  suggestions, and personal map colouring.
- A copy actively being read appears in the shared Reading area, while its
  retained shelf position remains stored. The map does not reveal the active
  reader's name in its location label.
- Suggestions only offer books that are `Pending` for the selected Owner and
  physically available. An active reading by another Owner therefore excludes
  the copy.

## 3. Canonical persistence model

Add a `reading_sessions` table with:

- UUID primary key;
- `library_id`, `book_id`, and `user_id` with composite scope constraints;
- state limited to active or completed;
- nullable `started_date` and `finished_date`;
- explicit `dates_unknown`;
- creation and modification timestamps.

Database checks must enforce:

- active session: known start, no finish, `dates_unknown = false`;
- completed known session: both dates present and finish not before start;
- completed unknown session: both dates null and `dates_unknown = true`;
- no half-known completed dates.

Partial unique indexes enforce one active session per physical book and one
unknown session per Owner/book. The service transaction enforces overlap and
same-day ambiguity rules under locking; database constraints remain the final
race-condition barrier.

Add a sparse Owner/book personal record for the Goodreads URL. Personal
reading state should normally be derived from sessions rather than duplicated:

- active first session → `Reading...`;
- active session after a completed one → `Re-Reading...`;
- no active session plus at least one completed session → `Read`;
- no sessions → `Pending`.

`BEING_READ` is likewise derived from the globally active session for the copy,
not stored as a second mutable status that could drift.

## 4. Migration safety protocol

1. Create a short-lived Phase 5 feature branch from current `main`.
2. Record commit SHA, Alembic head, table counts, and dormant Goodreads values.
3. Create a timestamped PostgreSQL `pg_dump` and verify that it can be listed
   and restored into a disposable database.
4. Add one reversible, additive Alembic migration; do not delete or reinterpret
   existing columns in the first migration.
5. Rehearse upgrade, invariant checks, downgrade, and second upgrade on the
   disposable database.
6. Run cross-library, cross-user, race, and authorization tests before applying
   the migration to development data.
7. Apply to development only after the migration gate passes. Keep the backup
   and compatibility column until the whole phase is accepted.

No command in this protocol opens or migrates the populated Local SQLite
catalogue.

## 5. Implementation increments

### 5A — schema and pure domain rules

- [x] Add reading-session and personal-book-record tables and relationships.
- [x] Implement pure state, chronology, duration, and display-counter helpers.
- [x] Add migration round-trip, invariant, and race-oriented database tests.
- [x] Expose nothing in the frontend yet.

Gate: migrations are reversible; existing Server counts and values are
unchanged; invalid date shapes and duplicate active/unknown sessions fail.

Verified implementation record (2026-09-06): migration
`0012_personal_readings` was backed up with a verified PostgreSQL custom dump,
restored into a disposable rehearsal database, upgraded, downgraded to
`0011_explicit_shelves`, and upgraded again. Existing development counts were
unchanged after applying 0012; `reading_sessions` and `personal_book_records`
were created empty. PostgreSQL concurrency testing proves that exactly one of
two simultaneous starts for the same physical copy can succeed. Pure tests
cover valid and invalid date shapes, overlap/boundary rules, unknown history,
derived personal states, inclusive duration/rates, ordering, and the agreed
active-reading counter notation.

### 5B — scoped services and API projections

- [x] Add list/start/finish/cancel/add-historical/edit/delete session commands.
- [x] Add personal Goodreads read/write commands.
- [x] Lock the physical copy when starting a session.
- [x] Return personal reading and shared custody as separate projections.
- [x] Enforce Owner-self writes and member read-only access.

Gate: two Owners see distinct histories for one shared copy; neither can write
the other's; concurrent starts produce one success and one controlled failure.

Verified implementation record (2026-09-06): scoped services and `/api/v1`
routes expose paginated chronological projections, self-only Owner commands,
member-readable Owner reviews, CSRF-protected writes, audit events, and hidden
cross-library failures. Automated API coverage uses two Owners, one Viewer and
one outsider. The PostgreSQL gate invokes the real service concurrently and
confirms one successful start plus one controlled conflict for a single copy.

### 5C — catalogue and reading-history experience

- Add perspective-aware status badges and start/finish/reread confirmations.
- Add chronological summary and full read-only history.
- Add self-only history management with destructive warnings.
- Add member-labelled Goodreads reviews and self-only editing.
- Adapt hero/current-reading counters, including the agreed `1+1` and `+2`
  rereading notation.

Gate: desktop and mobile Owner/Viewer acceptance across first reading,
rereading, cancellation, historical unknown dates, editing, deletion, and
perspective changes.

### 5D — map, statistics, filters, and suggestions

- Move an actively read copy visually to Reading while retaining its position.
- Make map colours and statistics use the selected perspective.
- Add advanced rereading filters and session-aware date results.
- Count reading events/pages correctly while preserving unique-book totals.
- Exclude physically unavailable copies from suggestions.

Gate: catalogue, map, statistics, and suggestions agree for two Owners with
different histories and one shared physical copy.

### 5E — compatibility cleanup and full acceptance

- Audit dormant shared Goodreads data and migrate it only through an explicit,
  reviewed mapping to an Owner.
- Remove compatibility paths only after zero-loss checks.
- Run complete backend/frontend, migration, authorization, responsive, and
  regression suites.
- Update all user and operator documentation before merge.

Gate: explicit user acceptance, then commit, push, and merge; no Phase 6 work is
mixed into the branch.

## 6. API projection rule

Never overload one `status` field. A book response should expose conceptually:

```text
reading: selected Owner's state and session summary
custody: shared physical availability and retained location
```

This permits, for example, Luis to see a book as personally `Read` while the
same copy is currently `BEING_READ` by another Owner. Viewer-safe projections
must omit write affordances, not fabricate a different domain state.

## 7. Verification matrix

Automated coverage must include:

- migration upgrade/downgrade and preservation of all existing records;
- session shape, overlap, unknown-date, chronology, and same-day boundaries;
- concurrent starts and stale updates;
- Owner-self, other-Owner, Viewer, outsider, and cross-library authorization;
- distinct perspectives for catalogue, map, statistics, and suggestions;
- unique-book versus reading-event/page totals;
- missing page counts;
- retained shelf position and shared Reading-area custody;
- Goodreads ownership and member-readable projection;
- CSRF, audit events, pagination, and mobile-safe API failures.

Manual acceptance uses at least two Owners and one Viewer on desktop and phone.

## 8. Token-aware delivery plan

Observed session cost suggests these approximate budgets:

- 5A: 30–40% of a full context;
- 5B: 25–35%;
- 5C: 30–40%;
- 5D: 35–50%;
- 5E: 15–25%.

The whole phase is therefore roughly 1.5–2.5 full contexts, depending on defects
found during manual acceptance. With less than half a context available, the
safe work is documentation, read-only preflight, backup, and branch creation;
starting a live migration plus its full verification is poor risk management.
The recommended next coding session starts near a full budget and completes 5A
as one coherent migration gate.

## 9. Resolved frontend contract

The Server experience will follow these agreed rules:

- Add Local-style personal-state labels to catalogue rows, calculated for the
  selected reading perspective. The labels are clickable only when the signed-in
  Owner is viewing their own perspective. An Owner viewing another Owner's
  perspective, and every Viewer, receives the same read-only state without a
  start, finish, reread, cancel, or history-write action.
- Keep a compact `New read` and Suggestions action beside the catalogue's Add
  action. A status-label click remains the contextual shortcut for starting,
  finishing, or rereading that particular book.
- Separate shared `Edit book metadata` from personal `My reading` using two
  distinct buttons and icons. `My reading` owns personal session management and
  the signed-in Owner's Goodreads review URL; shared Edit never mutates a
  personal reading record.
- Display personal state and shared custody simultaneously. For example, Luis
  may see personal state `Read` while the location reports `Being read` because
  Ana has the physical copy. The retained shelf position remains available,
  and the custody presentation does not identify the active reader.
- Show every actively read physical copy in the shared Reading area regardless
  of selected perspective. Perspective changes personal colour and inspection
  data, not the copy's physical custody.
- Add Statistics to the compact Catalogue/Map view selector. Suggestions remain
  a catalogue action rather than a separate large workspace or hero.
- In the main catalogue row, show a Goodreads action only when the selected
  perspective's Owner has saved a URL. Complete information lists every saved
  Owner review, labelled by visible username, and entirely omits Owners who
  have no URL instead of rendering empty placeholders.
- Start and finish dialogs propose today's date while allowing the writing
  Owner to change it before confirmation. All canonical chronology and
  concurrency validation still runs on submission.
