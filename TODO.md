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
- [x] Mark a read book's finished-reading date as explicitly unknown.
- [x] Keep acquisition and reading dates chronologically consistent.
- [x] Add read-only external maintenance checks for lifecycle dates and
  Goodreads links.

## A. Features possible with the current database

These features can use the fields and relationships already stored. They may
require backend or frontend work, but do not require adding catalogue data
fields.

### Data safety and documentation

- [ ] Document manual recovery procedures and recommendations for storing
  backups safely.

### Reading status and physical location

- [ ] Preserve a book's saved container and position when its status changes
  to `Reading...`.
  - Show the book in the separate reading area on the visual map.
  - Do not clear its physical location unless the user explicitly edits it.
  - Ensure returning the book to the shelf does not disturb other positions
    unnecessarily.

### Visual-map improvements using existing data

- [ ] Add direct drag-and-resize handles as an optional alternative to the
  current precise slider controls.
- [ ] Add visual-map colouring modes derived from existing fields:
  - Reading status.
  - Acquisition-date recency.
  - Finished-reading-date recency.
  - Time spent pending, when acquisition and reading-started dates are known.
  - Reading duration, when reading-started and finished-reading dates are
    known.
  - Use a clear legend and consistent light-to-dark scales.
- [ ] Keep visual book dragging and visual reordering as a possible future
  improvement; it is outside the current read-only visual-map scope.

### Faster book capture

- [ ] Scan an ISBN/barcode from a phone as described in `SCANNING_PLAN.md`.
- [ ] Use the scanned code to look up title and author without storing new
  metadata.
- [ ] Integrate scanning into Batch Add while preserving its current container,
  position, and direction.
- [ ] Add OCR later as a fallback for books without a usable barcode.

### Search, filters, and data-quality views

- [ ] Add explicit unknown/missing-date filters:
  - Read books with an unknown finished-reading date.
  - Books with an unknown acquisition date.
  - An option for date-range filters to include unknown-date books.
- [ ] Add quick views for:
  - Books without a physical location.
  - Books without a cover.
  - Books with missing dates.

### Suggestions and statistics using existing data

- [ ] Suggest a random pending book.
- [ ] Suggest the oldest pending book.
- [ ] Filter suggestions by time spent pending.
- [ ] Show books read by month and year.
- [ ] Show average time spent pending.
- [ ] Show average reading duration.
- [ ] Compare books acquired with books read.
- [ ] Compare the original collection with later acquisitions.

### Physical-library maintenance

- [ ] Edit bookcase names and descriptions.
- [ ] Renumber shelves.
- [ ] Renumber containers.
- [ ] Renumber book positions while preserving a continuous sequence and
  resolving collisions safely.

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
