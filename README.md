# BOOKPILE

BOOKPILE is a local-first personal library manager for cataloguing books,
recording reading history, and finding each physical copy in a real room.

It is currently a single-user application intended to run on a Windows PC and
be used from that computer or from a phone on the same private Wi-Fi network.
The catalogue, covers, and physical layout remain under the user's control.

## Current capabilities

### Catalogue and reading history

- Create, edit, delete, search, sort, and filter books.
- Keep the immediate search focused on title, author, and series, with ISBN and
  optional metadata available through **Sort & Advanced Search**.
- Track `Pending`, `Reading...`, and `Read` status.
- Record acquisition, reading-started, and finished-reading dates.
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
  crowding the main list with additional metadata.
- Add books individually or through Batch Add, retaining the selected
  container and advancing positions upward or downward.

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
- A projected map and grouped movement history before applying anything.
- Atomic Apply, Undo, Cancel, stale-preview protection, and rejection of
  unfinished chains or persistent gaps.
- Explicit status confirmation when moving books into or out of the Reading
  area.

### Visual library map

- Display furniture, shelves, foreground/background containers, and books as
  a room-scale visual index.
- Position and resize furniture and the separate Reading area.
- Customize relative shelf heights and each container's position, width, and
  height.
- Allow controlled foreground/background overlap while preventing accidental
  same-layer container overlap.
- Preserve the visual layout independently from catalogue locations.
- Open the catalogue filtered by a bookcase, shelf, or container.
- Click an individual visual book to open its exact catalogue record.
- Open the map from a catalogue location and highlight one book while fading
  the rest.
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
copies remain allowed. OCR still supplies reviewed Title and Author text only.
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
- Start or finish reading through confirmation prompts without losing the
  physical position.

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

## Technology

- Backend: FastAPI, SQLite, Pillow, and pillow-heif.
- Frontend: React, TypeScript, and Vite.
- Barcode decoding: ZXing in the browser.
- Temporary cover OCR: Tesseract.js in the browser.

## Running BOOKPILE

### Recommended launcher

From the project root:

```powershell
.\start-bookpile.ps1
```

The launcher starts the backend and optimized frontend, then displays the LAN
URL for this computer and other devices on the same Wi-Fi.

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
npm run lint
npm run build
```

Automated provider tests use mocked responses and do not depend on live
third-party services.

## Project documentation

- `TODO.md` is the authoritative roadmap and separates work possible with the
  current database from schema expansion and product-scale development.
- `SCANNING_PLAN.md` documents ISBN, barcode, OCR, catalogue matching, and
  future live-camera work.
- `BACKUP_EXPORT_PLAN.md` documents the backup format, restore validation, and
  CSV export design.
- `MIGRATION_RECOVERY.md` documents versioned schema changes, isolated
  rehearsals, mandatory pre-migration backups, and recovery.
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

Later database phases include richer bibliographic metadata, structured
authors, reading-session history and re-reading, and optional loan history.
Multi-user accounts and publication as a hosted application are a separate,
larger product phase rather than assumptions in the current local-first build.
