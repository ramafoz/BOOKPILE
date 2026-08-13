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
- [x] Add visual book rearrangement to the library map.
  - Choose the old-position and new-position behaviours before selecting a
    book.
  - Select books on pointer-down and choose destinations visually or through
    precise container-and-position controls.
  - Support continuous press-and-drag with a visible book ghost, while
    retaining sequential tap-based operation for mobile browsers.
  - Support collapsing or temporarily retaining the old gap.
  - Support squeezing, swapping, and chained continuation at occupied
    destinations.
  - Allow several completed movement chains to be assembled against the
    projected layout before one atomic Apply.
  - Group the preview as Move 1, Move 2, and so on, and summarize automatic
    shifts by count instead of listing every shifted book.
  - Explain when a sequence cancels itself out and leaves no net changes to
    apply.
  - Preview every affected movement and require explicit Apply or Cancel.
  - Reject incomplete chains, persistent gaps, stale previews, and invalid
    destinations without changing the catalogue.
  - Keep the entire Apply operation atomic.
  - Move Pending books into the Reading area without losing their retained
    physical position.
  - Present explicit Pending and Read choices when returning a Reading book to
    the physical library, then resume the pending destination preview.
  - Keep Read-to-Reading moves unavailable until reading sessions and
    re-reading are supported.

### Catalogue entry, dates, sorting, and filtering

- [x] Add a dedicated Batch Add workflow.
- [x] Preserve the selected container and useful repeated values between
  consecutive Batch Add entries.
- [x] Advance physical positions automatically in ascending or descending
  order.
- [x] Clear title-, author-, and ISBN-specific values between Batch Add entries.
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
- [x] Open a read-only complete-information dialog from each catalogue row,
  including identifiers, dates, status, location, notes, links, cover state,
  and record timestamps without expanding the main list.
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

### Faster book capture

- [x] Implement the shared recognition and catalogue-matching foundation in
  `SCANNING_PLAN.md`.
  - Normalize and validate ISBN-10 and ISBN-13.
  - Normalize external provider responses into a future-ready candidate shape.
  - Compare recognized books with the current catalogue using Title/Author and
    show strong, possible, or no-match outcomes.
  - Open a likely existing record, or suggest adding a new book when no match
    is found.
- [x] Add typed/pasted ISBN lookup to Add Book and Batch Add.
  - Apply reviewed Title, Author, ISBN-10, and ISBN-13 values to the form.
  - Keep all lookup results reviewable and never write automatically.
- [x] Decode an ISBN barcode from a temporary phone photograph.
  - Prefer browser-side decoding that works over the current local Wi-Fi URL.
  - Discard the image after recognition and keep it separate from the stored
    cover photograph.
- [x] Integrate ISBN lookup and temporary-photo barcode capture into Batch Add
  while preserving its current container, position, direction, and collision
  handling.
- [x] Add optional OCR from a temporary front-cover photograph.
  - Let the user select or correct recognized Title and Author text.
  - Optionally resolve the corrected text against bibliographic providers.
  - Check catalogue matches before suggesting addition.
- [ ] Evaluate live continuous barcode scanning as a later capture mode.
  - First provide and validate a trusted HTTPS or installable-app approach for
    phone camera-stream access.
  - Keep typed ISBN and temporary-photo scanning as permanent fallbacks.
  - Stop camera streams reliably and debounce repeated detections.
- [ ] Very long-term: evaluate a more capable OCR experience only if its
  practical value justifies the complexity.
  - Consider user-selected image regions, live framing guidance, or
    platform-native text recognition in a future installable/native app.
  - Keep the current temporary-photo OCR as the simple, private fallback.

## B. Features requiring a safe database expansion

These features need new book fields, related records, or historical data.
Before implementing any of them, introduce a repeatable migration process that
protects the completed catalogue.

### Safe schema-expansion prerequisite

- [x] Add versioned database migrations with explicit approval and transactional
  rollback.
- [x] Create and validate an automatic full ZIP backup before every migration.
- [x] Prefer additive, nullable fields and new related tables so all existing
  books remain valid without placeholder data.
- [x] Test migrations against a copy of the populated database and verify:
  - Book, hierarchy, layout, date, link, and cover counts.
  - Existing catalogue values before and after migration.
  - Backup export and restore compatibility.
- [x] Record the detected database schema version in backups.
- [x] Document inspection, rehearsal, approval, and failed-migration recovery in
  `MIGRATION_RECOVERY.md`.

### Structured authors

- [x] Implement, rehearse, and apply the additive v3-to-v4 structured-author
  migration to the populated catalogue with all existing values and covers
  preserved and without inferring authors from legacy text.
- [x] Supplement the original free-text author value with structured author records
  while preserving the original text during migration.
- [x] Support up to 250 authors per book and preserve their display order.
- [x] Validate the canonical `Multiple authors` marker, a minimum of two names,
  normalized duplicate names, ordered editing, and safe conversion back to a
  single-author record.
- [x] Show both names directly for two-author books.
- [x] For larger groups, show a clickable `Multiple authors` label.
- [x] Open an integrated pop-up containing the complete author list.
- [x] Include a book in simple search results when any structured author matches.
- [x] Add an advanced filter for single- or multiple-author records.
- [x] Let reviewed ISBN results initialize multiple-author records while warning
  the user to exclude translators, editors, and illustrators.
- [x] Preserve ordered structured authors in full backups and CSV export.

### Additional book metadata

- [x] Implement, rehearse, and apply the additive v2-to-v3 metadata migration
  to the populated catalogue with all existing values and covers preserved.
- [x] Add optional subtitle and number of pages.
- [x] Complete optional normalized ISBN-10 and ISBN-13 identifiers end to end.
  - [x] Add nullable indexed storage through the live v1-to-v2 migration.
  - [x] Expose ISBN fields through book APIs, editing, addition, and reviewed
    scanning-result acceptance.
  - [x] Index ISBNs for exact matching but allow intentional duplicate copies.
  - [x] Distinguish an exact-edition ISBN match from a probable same-work
    Title/Author match.
- [x] Add optional publisher.
- [x] Add the four-digit year of the current edition and the original
  publication year as separate optional values.
- [x] Add optional free-text language.
- [x] Add an optional positive edition number.
- [x] Add optional series name and free-text series volume.
- [x] Add a controlled binding classification independently from publication
  type.
- [x] Add a controlled publication type including conventional book, comic or
  graphic novel, atlas, reference work, illustrated/art book, and periodical.
- [ ] Add structured subjects.
- [ ] Add structured genres; v3 preserves an optional free-text genre value as
  an interim source for a later lossless conversion.
- [x] Add a fiction/non-fiction classification.
- [ ] Add free-form tags.
- [ ] Add an optional personal rating.
- [x] Allow reviewed ISBN results to populate selected supported metadata,
  leaving inferred classifications unchecked and every applied value editable
  before saving.

### Features enabled by additional metadata

- [x] Add visual-map colouring modes for:
  - Language.
  - Fiction/non-fiction.
  - Current-edition and original-publication years.
  - Binding and publication type.
  - A selected-genre focus that fades books outside that genre.
  - Per-book reading rate in pages per inclusive reading day.
- [ ] Add personal-rating colouring after ratings exist.
- [x] Give every implemented colouring mode a clear legend.
- [x] Keep the simple catalogue search limited to title, author, and series.
- [x] Add combinable advanced catalogue filters for exact ISBN and existing
  metadata values, with OR inside one category and AND across categories.
- [x] Add inclusive minimum/maximum filters for page count and either current-
  edition or original-publication year.
- [x] Filter read-only statistics with the same metadata rules, allowing views
  such as Galician-language books read in a selected year.
- [ ] Extend metadata filtering to reading suggestions.
- [ ] Add later near-match suggestions and a deliberate normalization strategy
  for free-text language and genre values, especially before a multilingual UI.
- [x] Estimate pages read by month and year by distributing pages over each
  reading interval; use the finish day when the start date is unknown.
- [x] Show estimated pages per week and month with sample and exclusion counts.
- [x] Show average, median, and individual per-book reading rates, respecting
  the selected year and metadata filters and marking one-day estimates.
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

- [ ] Add a localization framework only after the main interface and data
  model are mature; keep the current interface in English until then.
  - Planned interface languages: Galician, Portuguese, Spanish, Italian,
    Catalan, Basque, French, and Chinese, in addition to English.
  - Design normalization and display rules for free-text metadata before
    localized labels or translated controlled vocabularies are introduced.

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
- [N] Persistent empty-position markers on the normal visual map. Temporary
  destination slots are shown only while visual rearrangement is active.
- [N] Visual duplicate/conflicting-position warnings.
