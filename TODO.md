# BOOKPILE Roadmap

This roadmap separates future work by its effect on the current data model.

- `[x]` Implemented.
- `[ ]` Planned or under consideration.
- `[N]` Explicitly not planned.

## Implemented foundation

### Backup and data portability

- [x] Create a downloadable backup containing:
  - The SQLite catalogue database.
  - All locally stored cover images.
  - Backup metadata and a format version.
- [x] Add a controlled restore flow.
- [x] Validate backup integrity before restoring.
- [x] Create an automatic safety backup before every restore.
- [x] Export the catalogue to CSV.

### Visual library

- [x] Build a read-only visual index of bookcases, shelves, containers, and
  status-coloured books.
- [x] Keep overlapping background and foreground containers simultaneously
  visible.
- [x] Use lighter background styling only when a foreground layer obscures it.
- [x] Show rows horizontally and piles vertically.
- [x] Open the catalogue, filtered and sorted by physical position, when a
  bookcase, shelf, or container is clicked.
- [x] Keep individual books non-clickable in the general visual index.
- [x] Allow persistent physical gaps between containers.
- [x] Position and scale furniture relative to other furniture.
- [x] Resize shelves within furniture using relative height weights.
- [x] Reposition containers and customize their width and height.
- [x] Allow foreground containers to overlap up to 50% of a background row's
  height.
- [x] Persist the visual layout independently from catalogue locations.
- [x] Render containers as grey rectangles filled with books.
- [x] Colour books according to reading status.
- [x] Open the visual map from a catalogue location, highlight the selected
  book, and fade all other books.
- [x] Open the main catalogue with an exact-book filter when an individual book
  is clicked on the visual map.
- [x] Preserve a book's saved container and position while its status is
  `Reading...`, showing it only in the separate reading area on the visual map
  unless the user explicitly edits its physical location.
- [x] Add direct layout handles alongside the precise sliders:
  - Move and resize furniture and the Reading area.
  - Move and resize containers.
  - Resize adjacent shelves by dragging their divider.
- [x] Add visual-map colouring modes derived from existing data:
  - Reading status.
  - Acquisition-date recency.
  - Finished-reading-date recency.
  - Time spent pending.
  - Reading duration.
  - Use a 1st–99th percentile-clipped light-blue-to-deep-red scale so outliers
    do not flatten the useful visual range.
  - Identify unique oldest/newest or shortest/longest books in each legend.
  - Count same-day date intervals as one day.
  - Distinguish Pending, Reading, and Read-with-missing-data states where a
    duration or finished-reading date is not applicable or unavailable.
  - Use a background-like neutral missing-data colour and a mode-specific
    legend.
- [x] Prevent containers in the same shelf and layer from gaining visual
  overlap through either direct manipulation or precise sliders.
  - Continue allowing overlap between background and foreground layers.
  - Validate the same rule in the backend before saving a layout.

### Catalogue entry, dates, sorting, and filtering

- [x] Add a dedicated Batch Add workflow.
- [x] Preserve the selected container and useful repeated values between
  consecutive Batch Add entries.
- [x] Advance physical positions automatically in ascending or descending
  order.
- [x] Clear title- and author-specific values between Batch Add entries.
- [x] Allow leaving Batch Add without affecting normal single-book entry.
- [x] Sort by physical position, title, author, acquisition date,
  reading-started date, or finished-reading date.
- [x] Support ascending and descending sorting.
- [x] Filter by physical location using cascading bookcase, shelf, and
  container selectors.
- [x] Filter by optional from/to ranges for acquisition, reading-started, or
  finished-reading dates.
- [x] Independently include books with an unknown selected date in date-range
  results or an unknown sorted date in date-sorted results.
- [x] Add normal quick views for Read books with an unknown finished-reading
  date and books belonging to the Original Collection.
- [x] Add separate catalogue-cleanup checks for Read books whose known
  reading interval is missing one endpoint, and for books with no physical
  location or no cover.
- [x] Show how many books match the active catalogue filters.
- [x] Treat unknown dates as earlier than all known dates when sorting any
  lifecycle date, while allowing unknown-date books to be excluded.
- [x] Mark a read book's finished-reading date as explicitly unknown.
- [x] Keep acquisition and reading dates chronologically consistent.
- [x] Add read-only external maintenance checks for lifecycle dates and
  Goodreads links.

### Physical-library maintenance

- [x] Keep bookcase, shelf, and container maintenance inside Library Layout.
- [x] Edit bookcase names and descriptions.
- [x] Renumber shelves, swapping occupied numbers safely.
- [x] Renumber containers, swapping occupied numbers safely within the same
  shelf, layer, and container type.
- [x] Renumber book positions while preserving a continuous sequence and
  resolving collisions safely.

### Navigation and primary actions

- [x] Reorder the top navigation as `Library map`, `Statistics`, and
  `Settings`.
- [x] Open a Settings menu containing:
  - `Customize library layout`, opening the existing Library Layout dialog.
  - `Data & backups`, opening the existing backup/export/restore dialog.
- [x] Replace the current standalone and catalogue-level add controls with a
  consistent hero action row below the introductory text.
  - Add an `Add` menu with `Add single book`, `Add Batch`, and `Reorganize`.
  - Add a `New read` menu containing the suggestion entry points.
  - Remove the duplicate Batch Add, Reorganize, and Add Book buttons from the
    catalogue heading.
  - Keep both menus usable on mobile and reserve enough desktop hero height so
    they never overlap the summary counters.
  - Support closing menus by selecting an item, clicking outside, or pressing
    Escape, and expose appropriate accessible menu state.

### Reading suggestions using existing data

- [x] Open an integrated suggestion dialog from the hero's `New read` menu.
- [x] Suggest a random Pending book.
- [x] Suggest the oldest Pending book whose acquisition date is known.
- [x] Suggest among Pending books using a minimum time-pending threshold.
  - Calculate time pending from acquisition date through today.
  - Clearly separate books with unknown acquisition dates instead of assigning
    them an invented waiting time.
- [x] Show the suggested book's cover, title, author, location, acquisition
  information, and current waiting time where known.
- [x] Allow another suggestion without closing the dialog and avoid repeating
  a book until the current candidate set has been exhausted.
- [x] Allow opening the exact catalogue record from a suggestion.
- [x] Offer `Start reading` only after explicit confirmation, using the
  existing status/date update rules and preserving the saved physical
  location.
- [x] Add read-only suggestion API tests; no schema changes are required.

### Statistics using existing data

- [x] Add a top-level Statistics tab/view that does not alter catalogue data.
- [x] Add a read-only statistics API so calculations and missing-data rules
  are consistent across desktop and mobile.
- [x] Show the total number of books read by month and year using known
  finished-reading dates.
- [x] Show average and median time spent pending for books with both
  acquisition and reading-started dates.
- [x] Show average and median reading duration for books with both
  reading-started and finished-reading dates, counting same-day reading as one
  day.
- [x] Compare books acquired with books read by month and year.
- [x] Compare the Original Collection with later acquisitions using totals and
  Pending/Reading/Read status breakdowns.
- [x] Display the sample size beside every date-derived statistic and disclose
  how many books were excluded because a required date is unknown.
- [x] Provide year and all-time controls without adding or modifying database
  fields.
- [x] Add backend calculation tests covering unknown dates, same-day reading,
  empty periods, and Original Collection records.

### Status action prompts using existing data

- [x] Make a Pending status label clickable and open a `Start reading?`
  confirmation dialog.
- [x] Make a Reading status label clickable and open a `Did you finish?`
  confirmation dialog.
- [x] Reuse the existing lifecycle-date validation and automatic date behavior
  when either action is confirmed.
- [x] Keep Read status labels non-interactive until reading-session history and
  safe re-reading support have been added.

## A. Features possible with the current database

These features can use the fields and relationships already stored. They may
require backend or frontend work, but do not require adding catalogue data
fields.

### Data safety and documentation

- [ ] Document manual recovery procedures and recommendations for storing
  backups safely.

### Visual-map future ideas

- [ ] Keep visual book dragging and visual reordering as a possible future
  improvement; it is outside the current read-only visual-map scope.

### Faster book capture

- [ ] Scan an ISBN/barcode from a phone as described in `SCANNING_PLAN.md`.
- [ ] Use the scanned code to look up title and author without storing new
  metadata.
- [ ] Integrate scanning into Batch Add while preserving its current container,
  position, and direction.
- [ ] Add OCR later as a fallback for books without a usable barcode.

## B. Features requiring a safe database expansion

These features need new book fields, related records, or historical data.
Before implementing any of them, introduce a repeatable migration process that
protects the completed catalogue.

### Safe schema-expansion prerequisite

- [ ] Add versioned database migrations.
- [ ] Create an automatic full ZIP backup before every migration.
- [ ] Prefer additive, nullable fields and new related tables so all existing
  books remain valid without placeholder data.
- [ ] Test migrations against a copy of the populated database and verify:
  - Book, hierarchy, layout, date, link, and cover counts.
  - Existing catalogue values before and after migration.
  - Backup export and restore compatibility.
- [ ] Record the database schema version in backups.
- [ ] Document recovery steps for a failed migration.

### Structured authors

- [ ] Replace the single free-text author value with structured author records
  while preserving the original text during migration.
- [ ] Support any number of authors per book and preserve their display order.
- [ ] Show both names directly for two-author books.
- [ ] For larger groups, show a clickable `Varios`/`Multiple authors` label.
- [ ] Open an integrated pop-up containing the complete author list.
- [ ] Include a book in search results when any contributing author matches.

### Additional book metadata

- [ ] Add optional number of pages.
- [ ] Add optional ISBN.
- [ ] Add optional publisher.
- [ ] Add optional publication year.
- [ ] Add optional language.
- [ ] Add optional edition.
- [ ] Add structured genres.
- [ ] Add a fiction/non-fiction classification.
- [ ] Add free-form tags.
- [ ] Add an optional personal rating.

### Features enabled by additional metadata

- [ ] Add visual-map colouring modes for:
  - Language.
  - Fiction/non-fiction.
  - Publication year.
  - Personal rating.
  - Other catalogue fields where a visual comparison is useful.
- [ ] Give every colouring mode a clear legend.
- [ ] Filter searches and reading suggestions by genre, page count, language,
  fiction/non-fiction, tags, or rating.
- [ ] Show pages read by month and year.
- [ ] Find books with incomplete optional metadata.

### Reading sessions and re-reading

- [ ] Add a related reading-session history instead of overwriting the single
  reading-started and finished-reading dates currently stored on each book.
- [ ] Migrate each existing known or explicitly unknown reading interval into
  an initial session without losing its original values.
- [ ] Allow multiple completed sessions and at most one active reading session
  per book.
- [ ] Preserve explicit unknown start/end information for historical sessions.
- [ ] Define how the book's displayed status and summary dates are derived from
  its latest session while retaining all earlier readings.
- [ ] After that migration, make a Read status label clickable and open a
  `Re-read?` confirmation dialog that creates a new session.
- [ ] Extend backups, restore validation, CSV export decisions, statistics,
  and tests to cover repeated readings.

### Loans and history

- [ ] Add an `On loan` state independent of the book's reading status, so
  lending a book does not replace `Pending`, `Reading...`, or `Read`.
- [ ] Record the borrower and loan date.
- [ ] Record an optional expected return date and the eventual actual return
  date.
- [ ] Display outstanding loans and overdue expected return dates.
- [ ] Add a separate visual-map area for books currently on loan.
  - Preserve each loaned book's saved physical location.
  - Return it to its normal map position when the active loan ends.
- [ ] Retain completed loans as optional history.
- [ ] Optionally retain a history of physical moves.

## C. Product-scale expansion: users and publication

This is a separate scale of project. It changes BOOKPILE from a trusted
single-user local application into a multi-user product exposed to the
internet. It requires product, privacy, security, hosting, and operational
decisions in addition to application code.

### Multi-user foundation

- [ ] Define the intended product model: self-hosted instance, hosted service,
  installable app, or a combination.
- [ ] Introduce user accounts with secure registration, sign-in, sign-out,
  password recovery, and session management.
- [ ] Assign every library, book, cover, hierarchy record, and visual layout to
  an owner.
- [ ] Migrate the current library safely to the first owner account.
- [ ] Enforce strict data separation between users.
- [ ] Give each user an independent catalogue, physical hierarchy, visual map,
  backup, restore, and export flow.

### Privacy and social features

- [ ] Define library visibility levels such as private, friends-only, or
  public.
- [ ] Define separate visibility controls for catalogue information and the
  physical map, since the map may reveal details about a user's home.
- [ ] Add friendship requests, acceptance, removal, and blocking.
- [ ] Create a privacy-safe public/friends catalogue view that can omit physical
  location and map information.

### Publishable web/app infrastructure

- [ ] Replace local-only assumptions with production configuration for the
  database, cover storage, API URLs, and secrets.
- [ ] Choose production hosting, a managed database, durable image storage,
  domain, and HTTPS.
- [ ] Add authorization checks to every user-owned backend operation.
- [ ] Add upload validation, rate limiting, security headers, audit logging,
  monitoring, and error reporting.
- [ ] Define storage limits, backup retention, account deletion, and data
  export policies.
- [ ] Add automated deployment, migration, test, and rollback procedures.
- [ ] Test responsive behaviour, accessibility, browser support, and mobile
  installation requirements.
- [ ] Prepare terms of use, privacy information, and any required consent or
  data-protection processes before accepting external users.

## Explicitly not planned

- [N] Excel export; CSV and full ZIP backups are sufficient.
- [N] Empty-position markers on the visual map.
- [N] Visual duplicate/conflicting-position warnings.
