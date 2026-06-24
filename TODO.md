# BOOKPILE Roadmap

## Next priority: backup and data portability

- [x] Create a downloadable backup containing:
  - SQLite catalogue database.
  - All locally stored cover images.
  - Backup metadata and format version.
- [x] Add a controlled restore flow.
- [x] Validate backup integrity before restoring.
- [x] Create an automatic safety backup before every restore.
- [x] Export the catalogue to CSV.
- [ ] Consider Excel export after CSV is stable.
- [ ] Document manual recovery and backup storage recommendations.

## Visual library representation

- [x] Build a read-only visual index of bookcases, shelves, containers, and
  status-coloured books.
- [x] Use an exploded shelf view so overlapping background and foreground
  containers remain simultaneously visible.
- [x] Render background containers with lighter styling only when a foreground
  layer actually obscures them.
- [x] Show rows horizontally and piles vertically.
- [x] Open the catalogue filtered by bookcase, shelf, or container when that
  hierarchy level is clicked.
- [x] Sort catalogue results by ascending physical position when opened from
  the visual map.
- [x] Do not make individual books clickable in the visual index.
- [x] Allow persistent physical gaps between containers.
- [ ] Show empty book positions where useful.
- [ ] Detect duplicate or conflicting positions visually.
- [x] Let the user position bookcases/furniture relative to one another.
- [x] Scale furniture to preserve approximate relative physical size.
- [x] Resize shelves within a bookcase using relative height weights.
- [x] Reposition and resize containers within a shelf.
- [x] Let every container have independently customizable height as well as
  width, so piles can sit above background rows in unused vertical space.
- [x] Allow visual container overlap: foreground containers may cover up to
  50% of a background row's height to simulate shelf depth.
- [x] Persist the visual layout independently from catalogue locations.
- [ ] Add direct drag-and-resize handles as an optional convenience over the
  current precise slider controls.
- [x] Render containers as grey rectangles that fill with books.
- [x] Colour books according to reading status.
- [x] Open the visual map from a catalogue location and highlight the selected
  book while fading all other books.
- [ ] Future-only idea: drag books between containers and reorder them visually.
  This is not part of the current visual-index scope.

## Batch catalogue entry

- [x] Add a dedicated batch-add workflow.
- [x] Keep the selected container between consecutive books.
- [x] Advance the physical position automatically after each saved book.
- [x] Let a batch advance through positions in ascending or descending order.
- [x] Keep useful repeated catalogue values while clearing title/author-specific
  fields.
- [x] Allow leaving batch mode without affecting normal single-book entry.

## Catalogue sorting and filtering

- [x] Sort by physical position.
- [x] Sort alphabetically by title.
- [x] Sort alphabetically by author.
- [x] Sort by acquisition date.
- [x] Sort by reading-started date.
- [x] Sort by finished-reading date.
- [x] Support ascending and descending order.
- [x] Filter by date ranges.
- [x] Filter by bookcase, shelf, or container.

## Loans

- [ ] Mark a book as loaned.
- [ ] Record who has it.
- [ ] Record the loan date.
- [ ] Display outstanding loans.
- [ ] Optionally record return dates and loan history.

## Additional cataloguing

- [x] Mark a read book's reading date as explicitly unknown.
- [x] Keep acquisition and reading dates chronologically consistent.
- [ ] ISBN.
- [ ] Publisher.
- [ ] Publication year.
- [ ] Language.
- [ ] Edition.
- [ ] Genres.
- [ ] Free-form tags.
- [ ] Personal rating.

## Faster book capture

- [ ] Scan ISBN or barcode from a phone (see `SCANNING_PLAN.md`).
- [ ] Look up title and author automatically.
- [ ] Integrate scanning into Batch Add while preserving container and position.
- [ ] Add OCR as a later fallback for books without usable barcodes.

## Reading suggestions

- [ ] Suggest a random pending book.
- [ ] Suggest the oldest pending book.
- [ ] Filter suggestions by genre, size, or time in the pending list.

## Statistics

- [ ] Books read by month and year.
- [ ] Average time spent pending.
- [ ] Average reading duration.
- [ ] Books acquired versus books read.
- [ ] Original collection versus later acquisitions.

## Advanced search and data quality

- [x] Add read-only external maintenance checks for lifecycle dates and
  Goodreads links.
- [ ] Search and filter by physical location.
- [ ] Filter by lifecycle dates.
- [ ] Filter by genres and tags.
- [ ] Find books without a physical location.
- [ ] Find books without a cover.
- [ ] Find books with missing dates.
- [ ] Find incomplete metadata.

## Physical map maintenance

- [ ] Edit bookcase names and descriptions.
- [ ] Renumber shelves.
- [ ] Renumber containers.
- [ ] Renumber book positions.
- [ ] Keep an optional history of physical moves.
