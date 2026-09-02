# BOOKPILE

BOOKPILE is a local-first personal library manager for cataloguing books,
recording reading history, and finding each physical copy in a real room.

It is currently a single-user application intended to run on a Windows PC and
be used from that computer or from a phone on the same private Wi-Fi network.
The catalogue, covers, and physical layout remain under the user's control.

BOOKPILE Local v1 is distributed as source with a guided Windows installer.
New users should begin with [INSTALLATION.md](INSTALLATION.md), then read the
[user guide](USER_GUIDE.md) and [backup guide](BACKUP_AND_RECOVERY.md).

## Current capabilities

### Catalogue and reading history

- Create, edit, delete, search, sort, and filter books.
- Keep the immediate search focused on title, author, and series, with ISBN and
  optional metadata available through **Sort & Advanced Search**.
- Track `Pending`, `Reading...`, `Re-Reading…`, and `Read` display states.
- Record acquisition, reading-started, and finished-reading dates.
- Preserve a chronological history of first readings and re-reads while the
  legacy summary dates remain synchronized with the active or latest session.
- Add, edit, cancel, and delete reading sessions with overlap, unknown-date,
  and destructive-change safeguards.
- Represent original-collection books whose acquisition date is unknown.
- Represent read books whose exact finished-reading date is unknown.
- Validate chronological consistency between lifecycle dates.
- Sort by title, author, physical position, or lifecycle dates in either
  direction.
- Filter by status, physical hierarchy, date ranges, known or unknown dates,
  and catalogue-quality checks.
- Combine exact existing metadata values across language, genre, publisher,
  fiction category, binding, publication type, and series; combine several
  values within a category and apply inclusive page/year ranges.
- Use quick views for missing covers, missing locations, and incomplete dates.
- See how many books pass the current filters.
- Open a read-only complete-information card for any catalogue book without
  crowding the main list with additional metadata. This card displays reading
  history but contains no catalogue-editing actions.
- Manage chronological reading sessions only from **Edit book**, with a
  responsive editor for known or explicitly unknown historical dates.
- Add books individually or through Batch Add, retaining the selected
  container and advancing positions upward or downward.
- Loan and return books without changing their reading status or losing their
  saved shelf position. Keep one active loan plus optional returned history,
  free-text borrower information, optional expected-return dates, and known or
  explicitly unknown actual dates.
- Show `On loan: <borrower>` directly in the catalogue while keeping the
  retained shelf location available without crowding the row. Loan history is
  read-only in complete information and editable only through **Edit book**.
- Filter and sort by loan availability, overdue state, borrower, loan-history
  scope, and loan/expected-return/returned dates. Quick views expose current
  and overdue loans.

### Physical library

BOOKPILE models the hierarchy as:

```text
Bookcase → Shelf → Container → Book position
```

A container can be a background or foreground row or pile. Rows run from left
to right; piles stack from top to bottom.

- Create and edit bookcases; create, renumber, inspect, and safely remove
  shelves and containers from the dedicated Library Layout interface.
- Insert books into occupied positions by shifting existing books safely.
- Keep container positions continuous during normal catalogue changes.
- Preserve a book's retained physical position while it is `Reading...`.
- Reorganize books using precise controls or directly on the visual map.

Visual rearrangement supports:

- Click/tap selection and continuous press-and-drag.
- `Collapse` or temporary `Leave gap` behaviour at the old position.
- `Squeeze`, `Swap`, or chained `Continue` behaviour at the destination.
- Several completed movement chains in one provisional draft.
- A projected map and grouped movement history before applying anything,
  including page-proportional ROW widths and PILE heights.
- Optional per-move `Release shelf space`, with a five-percent physical
  compression limit and validation of container collisions and pile support.
- Atomic Apply, Undo, Cancel, stale-preview protection, and rejection of
  unfinished chains, persistent gaps, or invalid projected geometry. Book
  positions and visual-container dimensions are committed together.
- Explicit status confirmation when moving books into or out of the Reading
  area.

### Visual library map

- Display furniture, shelves, foreground/background containers, and books as
  a room-scale visual index.
- Use a responsive full-screen viewport over an effectively unbounded world,
  with pan, zoom, vertical fit/reset, compact overlays, and a collapsible colour
  legend.
- Pan by dragging the map with a mouse or one finger, zoom with the mouse wheel
  or trackpad, and use an anchored two-finger pinch on touchscreens. The compact
  directional and zoom controls remain available from the collapsed camera
  button in the lower-right corner.
- Position and resize furniture and the separate Reading and On-loan areas.
- Edit unbounded top-level coordinates through direct handles or a floating,
  minimizable editor with explicit Save and Cancel actions.
- Customize relative shelf heights and each container's position, width, and
  height.
- Allow controlled foreground/background overlap while preventing accidental
  same-layer container overlap.
- Preserve the visual layout independently from catalogue locations.
- Open the catalogue filtered by a bookcase, shelf, or container.
- Click an individual visual book to open its exact catalogue record.
- Open the map from a catalogue location and highlight one book while fading
  the rest.
- Give an active loan visual priority over Reading while keeping both the
  reading session and the book's reserved physical position intact.
- Use the map-tools `Show retained shelf spaces` preference to reveal
  proportional outlined positions for Reading and On-loan books. With the
  default setting off, their ROW/PILE is only visually reduced; saved layout
  geometry is not changed. Rearrangement always displays the retained spaces.
- Show active readings as equal open-book icons on a small reading table,
  always reserving surface space for one more book. Show On-loan books as
  page-proportional vertical volumes inside a cloud-like out-of-library area.
- Colour visual books by:
  - Reading status.
  - Acquisition recency.
  - Finished-reading recency.
  - Time spent pending.
  - Reading duration.
  - Language.
  - Current-edition or original-publication year.
  - Fiction/non-fiction, binding, or publication type.
  - A selected genre, fading books outside the chosen genre.
  - Reading rate in pages per inclusive reading day.
- Use percentile-clipped colour scales and separate missing/not-applicable
  states so outliers do not flatten the useful range.

### Covers and capture aids

- Add, replace, and remove optimized cover photographs from desktop or mobile.
- Accept JPEG, PNG, WebP, and iPhone HEIC input within the configured size
  limit.
- Type or paste an ISBN and retrieve reviewed bibliographic candidates.
- Photograph a barcode temporarily on a phone and decode book ISBNs while
  rejecting non-book barcodes.
- Photograph a front cover temporarily and use optional OCR to prepare
  title/author text for review.
- Check recognized candidates against the existing catalogue before offering
  to add a book.
- Keep manual entry fully available when recognition or an external provider
  is unavailable.

ISBN lookup and barcode evidence can fill field-by-field reviewed identifiers
and bibliographic metadata in Add Book, Edit Book, and Batch Add. Direct
provider values are selected by default; inferred genre/category/publication
type suggestions are visibly marked and start unchecked. Stored identifiers
are normalized and used for exact-edition matching while intentional duplicate
copies remain allowed. Provider results with several explicit authors prepare
an ordered multiple-author record for review, with a reminder to exclude
translators, editors, and illustrators. OCR still supplies reviewed Title and
Author text only.
The user's own cover photograph remains authoritative; external cover images
are not imported.

### Suggestions and statistics

- Suggest a random pending book, the oldest pending book, or a book based on
  time spent pending.
- Exclude already-shown suggestions and open the selected catalogue record.
- Show read-only yearly and monthly acquisition/reading totals.
- Show known reading and pending-duration statistics with excluded-data
  counts.
- Filter statistics by the same optional metadata used by advanced catalogue
  search.
- Estimate pages read by year or month and pages per week/month by spreading a
  book's pages across its inclusive reading interval. When the start date is
  unknown, assign the pages to the known finish day and report that estimate.
- Compare individual, average, and median per-book pages/day for the selected
  year and metadata filters, with estimated one-day readings clearly marked.
- Compare original-collection and later-acquisition status totals.
- Show active, overdue, and completed loan totals, known loans by year, and
  the most frequently loaned books under the same metadata selection.
- Start or finish reading through confirmation prompts without losing the
  physical position.
- Exclude books currently on loan from reading suggestions and reject a new
  reading or re-reading until the book is returned.

### Backup, restore, and export

- Download a verified full ZIP backup containing:
  - The SQLite catalogue.
  - Every stored cover.
  - Integrity metadata and format version.
  - SHA-256 checksums.
- Inspect and validate a backup before restoration.
- Create an automatic safety backup before replacing the current catalogue.
- Restore the database and covers atomically with rollback protection.
- Export catalogue data, dates, links, and physical locations as an
  Excel-friendly CSV.
- Export reading history as a separate Excel-friendly CSV with one row per
  session, including re-reads, dates, duration, state, and pages/day where
  page-count metadata exists.
- Export active-loan fields with the books CSV and the complete loan history
  as a separate Excel-friendly CSV. The full ZIP remains the only restorable
  format.

## Technology

- Backend: FastAPI, SQLite, Pillow, and pillow-heif.
- Frontend: React, TypeScript, and Vite.
- Barcode decoding: ZXing in the browser.
- Temporary cover OCR: Tesseract.js in the browser.

## Running BOOKPILE

### First installation

Install 64-bit Python 3.11+ and Node.js 20+, extract the complete release ZIP,
then run from its permanent folder:

```powershell
Set-ExecutionPolicy -Scope Process RemoteSigned
.\install-bookpile.ps1
```

The installer creates private dependencies, builds the frontend, initializes
an empty catalogue only when needed, and creates Start/Stop desktop shortcuts.
It does not overwrite existing catalogue data. Full prerequisites and update
instructions are in [INSTALLATION.md](INSTALLATION.md).

### Recommended launcher

From the project root:

```powershell
.\start-bookpile.ps1
```

The launcher starts the backend and optimized frontend, then displays the LAN
URL for this computer and other devices on the same Wi-Fi. Without an active
home network it falls back to localhost for use on the computer itself.

For future starts, install the desktop shortcuts once:

```powershell
.\install-desktop-shortcuts.ps1
```

Then use:

- **Start BOOKPILE** to launch the application in the background, display the
  mobile URL, and copy it to the clipboard.
- **Stop BOOKPILE** to stop only BOOKPILE's processes.

Runtime logs are stored locally in `.bookpile-runtime/`.

### Use from a phone

Open the LAN address shown by the launcher, for example:

```text
http://192.168.1.50:5173
```

The phone and host computer must be on the same private Wi-Fi. The optimized
frontend proxies API requests to the backend, so no phone-side configuration
is required. If Windows asks about network access, allow it for private
networks only.

BOOKPILE currently uses local HTTP. Browser features that require a trusted
HTTPS context, such as continuous live-camera streams, remain deferred.

### Manual development start

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

The API is available at <http://localhost:8000> and its interactive
documentation at <http://localhost:8000/docs>.

Frontend, in a second terminal:

```powershell
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

## Data and safety

The live SQLite catalogue and cover images are intentionally excluded from
Git. The main local data lives under `backend/data/`.

Use **Settings → Data & backups → Download full backup** before major catalogue
work or application upgrades. A full ZIP is safer than copying only the SQLite
file because it also preserves covers and includes integrity information.

Generated backups under `backend/backups/`, runtime files, reports, and local
project context are also excluded from the repository where appropriate.

## Catalogue maintenance checks

The maintenance utilities are read-only and never modify the catalogue.
Double-click either launcher:

- `check-bookpile-dates.cmd` audits lifecycle chronology, unexplained missing
  dates, original-collection conflicts, and suspicious future dates.
- `check-bookpile-goodreads.cmd` checks URL uniqueness and helps compare
  Goodreads pages with BOOKPILE title and author data.

Reports are written as Excel-friendly CSV files under `maintenance/reports/`.
Goodreads review can open links one at a time in the default signed-in browser
and retain the decisions made so far.

For a network-only Goodreads report:

```powershell
backend\.venv\Scripts\python.exe maintenance\check_goodreads_links.py
```

For an immediate offline duplicate-URL check:

```powershell
backend\.venv\Scripts\python.exe maintenance\check_goodreads_links.py --duplicates-only
```

## Verification

Backend tests:

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Frontend checks:

```powershell
cd frontend
npm test
npm run lint
npm run build
```

Automated provider tests use mocked responses and do not depend on live
third-party services.

## Project documentation

- `INSTALLATION.md` is the end-user installation, update, and uninstall guide.
- `USER_GUIDE.md` explains normal catalogue, reading, loan, map, and statistics
  workflows.
- `BACKUP_AND_RECOVERY.md` defines the practical backup and restore routine.
- `TROUBLESHOOTING.md` covers common installation, startup, and LAN problems.
- `LIMITATIONS.md` states the security and product boundaries of Local v1.
- `RELEASE_NOTES.md` summarizes the Local v1.0.0 release for end users.
- `RELEASE_CHECKLIST.md` records automated and manual release gates.
- `TODO.md` is the authoritative roadmap and separates work possible with the
  current database from schema expansion and product-scale development.
- `SCANNING_PLAN.md` documents ISBN, barcode, OCR, catalogue matching, and
  future live-camera work.
- `BACKUP_EXPORT_PLAN.md` documents the backup format, restore validation, and
  CSV export design.
- `MIGRATION_RECOVERY.md` documents versioned schema changes, isolated
  rehearsals, mandatory pre-migration backups, and recovery.
- `MULTIUSER_IMPLEMENTATION_PLAN.md` defines the hosted product's identity,
  tenancy, privacy, quota, migration, and deployment roadmap.
- `CROSS_EDITION_DATA_MODEL.md` classifies shared and personal data, defines
  future contributors/languages/dimensions, and specifies versioned conversion
  from Local ZIPs into Server libraries.
- `PHYSICAL_GEOMETRY_PLAN.md` defines the approved single-geometry model for
  manual and millimetre-driven layouts, accordion containers, supports,
  physical warnings, Server implementation, and later controlled Local work.
- `docs/adr/` records architectural decisions that must remain traceable as
  BOOKPILE Server evolves.
- `server/README.md` documents the isolated Server foundation and its test
  workflow. This code never opens the Local catalogue database.
- `BOOKPILE_PROJECT_CONTEXT_LOCAL.md` contains detailed local project history
  and is intentionally excluded from Git.

## Near-term roadmap

The safe database-expansion foundation and incremental schema history are now
in place:

1. Migrations require explicit approval and run transactionally.
2. Every migration first creates and validates a full automatic backup.
3. The v1-to-v2 migration was rehearsed and then applied to the populated
   catalogue with all existing values preserved.
4. Backups record their detected schema version and recovery is documented in
   `MIGRATION_RECOVERY.md`.
5. Schema v2 adds optional normalized ISBN-10/ISBN-13 fields as the first small
   additive migration; API, Add/Edit/Batch forms, barcode acceptance, search,
   exact matching, and CSV export now use them.
6. Schema v3 adds nullable edition metadata, classification, binding,
   publication type, genre text, and series fields. It was rehearsed and then
   applied to the populated catalogue with all 432 books and covers preserved.
7. Schema v4 adds ordered structured authors while retaining the required
   legacy Author text. It was rehearsed and applied with all 432 books and
   covers preserved; existing author text was deliberately left untouched for
   manual review.
8. Schema v5 adds ordered reading sessions. The migration was rehearsed and
   applied from a validated v4 backup with all 432 books, 432 covers, and 441
   structured-author rows preserved. It reconstructed 262 initial sessions,
   keeps the legacy status/date columns synchronized, and adds re-reading,
   history management, session-aware statistics, and CSV export.
9. Schema v6 adds related loan history with at most one active loan per book.
   The migration was rehearsed from a validated v5 backup with all catalogue
   and reading-session values preserved. Loans remain independent from reading
   status and retained physical position, and are included in map, search,
   statistics, backup validation, and CSV exports. The complete desktop and
   mobile loan/return/history workflow has been manually validated.
10. Schema v7 recentres the visual-library world at horizontal coordinate zero
    and removes the old top-level `0–100` boundary. The migration changes only
    top-level visual X coordinates, was rehearsed against a validated v6 ZIP,
    and preserved all 434 books and related catalogue data with successful
    integrity and foreign-key checks.
11. Schema v8 adds visual row anchors and explicit pile support on either a
    shelf or a non-empty same-layer row. The migration was rehearsed against a
    verified v7 ZIP and applied with all 434 books and 434 covers preserved,
    successful integrity and foreign-key checks, and 18 shelf-supported plus 9
    row-supported piles. The map renders book thickness proportionally to page
    count within each container; missing values use the complete catalogue's
    arithmetic mean, falling back to 200 only when no page data exists.
12. Server schema v9 establishes the physical-geometry foundation without
    changing Local v1: versioned manual/physical modes, millimetre world
    coordinates, generic acyclic container supports, row anchors, and PILE
    alignment. The migration was backed up, rehearsed forwards and backwards,
    and applied with existing Server data preserved. The precise editor now
    presents millimetres only, including support-relative bottom clearance and
    shelf-relative anchor/alignment coordinates. Manual rendering remains
    isolated until physical projection and accordion behaviour are complete.

Later database phases include structured subjects and genres, ratings and
tags.
Multi-user accounts and publication as a hosted application are a separate,
larger product phase rather than assumptions in the current local-first build.
The agreed separation between stable BOOKPILE Local v1 and the hosted Server
edition, together with its co-ownership, Viewer privacy, personal reading,
quota, authentication, migration, and deployment roadmap, is documented in
[MULTIUSER_IMPLEMENTATION_PLAN.md](MULTIUSER_IMPLEMENTATION_PLAN.md).

The isolated Server edition has completed its Phase 3 membership foundation,
Phase 4A–4C shared catalogue foundation, and most of Phase 4D. Secure accounts can create and
join libraries as equal co-Owners or scoped read-only Viewers. PostgreSQL has
library-safe metadata, contributor, hierarchy, dimension, and layout
structures; the responsive Server catalogue now supports scoped reads,
Owner-only writes, complete metadata, ordered contributors, search, filters,
sorting, pagination, and authenticated private cover images. Owners can add,
replace, and remove covers; Viewers can see them only while signed in as
members. Uploads are size- and pixel-limited, decoded as real images, stripped
of metadata, resized, and re-encoded as private WebP objects. Their originals
are not retained and their storage keys are never exposed as public URLs.
Server now also provides Owner-maintained physical hierarchy, revisioned layout
geometry, scoped map access, responsive mouse/touch camera navigation,
page-proportional rendering, book/container inspection, catalogue-row physical
locations, per-book placement, and transactional visual rearrangement. The
rearrangement draft supports Collapse/Leave gap and Squeeze/Swap/Continue,
multiple completed movement chains, proportional geometry previews, undo,
explicit Apply, concurrency revision checks, and audit. Phase 4D remains open
for complete physical-mode projection, accordion and warning behaviour, and
floating/direct layout editing. Its schema-v9 foundation, per-axis dimension
fallbacks, millimetre editor, generic support validation, and manual/physical
rendering boundary are implemented and accepted. This does not
alter or replace Local v1. Personal readings, loans, backups, and Local ZIP
import remain pending for later Server phases.

The compact Server workspace increment is complete and accepted on desktop and
mobile. It provides anchored top-bar menus, accurate private/shared and
perspective-aware catalogue headings, atomic physical placement inside Add and
Edit, iterative Batch Add with retained destination, compact mobile map
controls, and queued self-expiring success notifications. Its design and
acceptance record are in
[SERVER_FRONTEND_UX_PLAN.md](SERVER_FRONTEND_UX_PLAN.md).

## Licence

Copyright © 2026 Javier Ramalleira Fernández.

BOOKPILE is free software licensed under the
[GNU Affero General Public License, version 3 or later](LICENSE)
(`AGPL-3.0-or-later`). You may use, study, modify, redistribute, and offer the
software as a service under the licence terms. Modified network versions must
offer their corresponding source to users interacting with them remotely.

BOOKPILE is provided without warranty. See [COPYRIGHT](COPYRIGHT) and
[LICENSE](LICENSE) for the complete notice and legal terms.
