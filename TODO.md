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

- [ ] Display bookcases, shelves, rows, and piles graphically.
- [ ] Reorganize books using drag and drop.
- [ ] Show empty positions and physical gaps.
- [ ] Detect duplicate or conflicting positions visually.
- [ ] Let the user position bookcases/furniture relative to one another.
- [ ] Scale furniture to preserve approximate relative physical size.
- [ ] Reorder and resize shelves within a bookcase.
- [ ] Reorder and resize containers within a shelf.
- [ ] Render containers as grey rectangles that fill with books.
- [ ] Colour books according to reading status.

## Batch catalogue entry

- [x] Add a dedicated batch-add workflow.
- [x] Keep the selected container between consecutive books.
- [x] Advance the physical position automatically after each saved book.
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

- [ ] ISBN.
- [ ] Publisher.
- [ ] Publication year.
- [ ] Language.
- [ ] Edition.
- [ ] Genres.
- [ ] Free-form tags.
- [ ] Personal rating.

## Faster book capture

- [ ] Scan ISBN or barcode from a phone.
- [ ] Look up title and author automatically.
- [ ] Retrieve cover and publication metadata automatically.
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
