# BOOKPILE Local v1 user guide

BOOKPILE catalogues what you own, records reading and loan history, and maps
each physical copy to its real location. The application stores its data on
the Windows computer that runs it.

## Start with a safe baseline

After installation, start BOOKPILE and open **Settings → Data & backups**.
If migrating an existing BOOKPILE catalogue, validate and restore its full ZIP
before adding new records. If starting empty, create the physical hierarchy
before assigning books.

## Model the physical library

Open **Settings → Customize library layout** and create:

```text
Bookcase → Shelf → Container → Book position
```

Containers are rows or piles and can be in the background or foreground. Use
this maintenance screen to create, edit, renumber, or remove physical
structures. Use the visual map editor to arrange their presentation.

## Add books

The hero **Add** menu provides:

- **Add single book** for an individual record.
- **Add batch** for shelf-by-shelf cataloguing while retaining the selected
  container and advancing positions.
- **Reorganize** through the Library Map for controlled physical movements.

Title and Author are mandatory. Other identifiers, bibliographic metadata,
dates, cover, status, notes, and location are optional unless the selected
workflow makes them necessary.

You may type an ISBN, photograph its barcode, or photograph a cover for OCR.
Recognition prepares editable suggestions; nothing is saved until you review
and submit the form. Your own cover photograph remains authoritative.

When inserting into an occupied position, BOOKPILE can shift later books to
make room. Batch Add can proceed upward or downward through a container.

## Browse and clean the catalogue

The immediate search matches title, author, structured co-authors, and series.
Use **Sort & Advanced Search** for ISBN, metadata combinations, numeric page or
year ranges, physical hierarchy, dates, loan state, re-reads, and data-quality
views.

Each row provides actions for complete read-only information, Goodreads when
present, loan/return, edit, and delete. Deletion always requires confirmation.
Use catalogue checks and quick views to locate missing covers, locations,
dates, or optional metadata.

## Reading and re-reading

The status label can start or finish a reading through a confirmation dialog.
Starting a reading does not erase the retained shelf location. A second active
reading displays as **Re-Reading…** while still belonging to the Reading tab.

Open **Edit book → Manage reading history** to add, edit, cancel, or delete
sessions. Historical readings may have both dates explicitly unknown under the
documented safeguards; active readings always have a known start date.

## Loans

Use the loan action on a catalogue row to record who holds a book, an optional
loan date, expected return, and notes. A loan does not change reading status or
forget the retained shelf location. Returning suggests today's date and keeps
the history. Active loans are excluded from reading suggestions.

## Library Map

The full-screen map provides:

- mouse, touch, and compact-button pan/zoom controls;
- visual focus and inspection by furniture, shelf, container, or book;
- metadata-based colour modes;
- page-proportional book thickness within each container;
- dedicated Reading and On-loan representations;
- a floating layout editor and atomic visual rearrangement workflow.

Inspection is read-only. Rearrangement previews all changes and validates
positions, gaps, container dimensions, collisions, and pile support before the
single **Apply** action writes anything.

## Suggestions and statistics

**New read** suggests available pending books using the selected strategy and
metadata filters. Statistics summarize acquisitions, reading sessions, pages,
rates, durations, re-reads, and loans. Unknown dates and missing page counts
are identified or excluded according to the displayed calculation notes.

## Back up regularly

Use a full ZIP—not CSV—as the recoverable copy. Keep backups outside the
application folder and on a second device or cloud account. Read
[BACKUP_AND_RECOVERY.md](BACKUP_AND_RECOVERY.md) before restoring or updating.

## Privacy and network use

Anyone who can reach the displayed LAN address while BOOKPILE is running may
be able to use the local application. Run it only on a trusted private network,
stop it after use, and never expose its ports to the internet. Local v1 has no
accounts or access controls.
