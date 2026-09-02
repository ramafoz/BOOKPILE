# BOOKPILE Server — compact workspace and catalogue workflow plan

Status: implemented and accepted on desktop and mobile on 2026-09-02 on
`feature/server-compact-workspace`.

## 1. Objective

Make the Server workspace substantially more compact and reduce repetitive
cataloguing work without weakening library isolation or changing the database
schema. The selected library, workspace, reading perspective, signed-in user,
membership controls, and catalogue identity must remain understandable on
desktop, phone, and tablet.

This increment covers:

- a compact top navigation shell;
- a concise catalogue heading whose wording reflects membership and filters;
- physical placement inside Add/Edit Book;
- removal of the separate placement action from catalogue rows;
- an iterative Server Batch Add workflow with a retained destination.

It does not implement personal reading data, physical-dimension geometry,
direct layout manipulation, backups, or Local ZIP import.

## 2. Agreed interaction model

### 2.1 Selected library control

- Replace `Your libraries` plus the repeated large library heading with one
  top button labelled with the selected library name.
- Show a small Owner or Viewer icon/status in that button.
- Its popover lists every accessible library and retains the existing create
  library and join-by-invitation actions.
- Changing library returns to its catalogue, closes transient panels, and
  preserves the existing authorization refresh behavior.

### 2.2 Workspace and reading-perspective control

- A neighbouring button combines the current workspace and reading
  perspective.
- Its compact label follows `Catalogue — self`, `Map — self`, or
  `Catalogue — username` / `Map — username` when viewing another Owner's
  perspective.
- A Viewer sees the selected Owner username rather than `self`.
- The popover has two explicit groups: available workspace (`Catalogue` and,
  when authorized, `Library Map`) and available reading perspectives.
- `Customize layout` is not a normal viewing workspace; it moves to Settings.
- Catalogue-only Viewers are never offered the map.

### 2.3 Account and Settings controls

- Show the signed-in username compactly in the top bar, with the protected
  session shield beside it. Remove the large `Welcome` presentation.
- Keep sign-out readily available without making it the dominant action.
- Add one Settings button. Its menu contains, according to authorization:
  - Members and invitations (Owner only).
  - Customize library layout (Owner only).
  - Sign out and sign out from every device.
  - Future backup, account, quota, and administration entries.
- Members and invitations remain one integrated panel. Mutations keep current
  password reauthentication and consequence warnings.

### 2.4 Catalogue identity

- Align an open-book icon with three compact lines: catalogue privacy label,
  title, and count.
- Use `Private catalogue` when the library has one member and `Shared
  catalogue` when it has more than one.
- Beside `Shared catalogue`, provide a small read-only member list showing
  visible usernames and Owner/Viewer status. Membership editing remains in
  Settings.
- Use `Your books` only when the signed-in Owner's own perspective is active.
  Otherwise use `<username>'s books`.
- With no active search or advanced filter, show `N books`. Use `N books
  match` only when filtering/searching actually changes the catalogue query.

## 3. Privacy-safe data requirements

The existing Owner member-management response is not automatically suitable
for every Viewer. Add or adapt a library-member summary read that:

- requires authenticated membership in the same library;
- returns only user ID, visible username, library role, and Viewer scope;
- never exposes email, tokens, password/security state, account invitations,
  or private platform administration data;
- keeps every membership mutation Owner-only and CSRF protected;
- returns `404` for a user outside the library, including when a UUID is known.

No schema migration is expected. Add isolation and Viewer-projection tests
before using this response for `Private/Shared catalogue`.

## 4. Integrated physical placement

### 4.1 Edit Book

- Move Bookcase, Shelf, Container, and Position into a collapsible `Physical
  location` section in the existing Edit Book dialog.
- Remove the separate map-pin edit action after parity is verified.
- Keep the location visible in the catalogue row.
- An Owner can choose no physical location explicitly.
- Existing occupied-position insertion and source compaction rules remain.

### 4.2 Add Book

- Offer the same physical-location section while creating a book.
- Default to no location until the Owner chooses one; clearly indicate that
  positioning is recommended but not bibliographically mandatory.
- Use a composed backend command so book creation and initial placement are
  validated and committed atomically. A failed placement must not leave a
  surprise unpositioned book.
- Private cover processing remains a separate post-create operation, retaining
  its current explicit partial-success message because binary object storage
  cannot share the catalogue database transaction.

## 5. Server Batch Add

- Add `Add batch` beside or inside the catalogue Add control.
- Save books iteratively rather than as one enormous transaction: each
  confirmed book is durable and a later failure does not erase earlier work.
- Retain Bookcase, Shelf, and Container after each successful addition.
- Propose the next end position after every save while still allowing insertion
  into an occupied position through the normal safe squeeze rule.
- Clear book-specific title, author/contributors, identifiers, metadata, cover,
  and position override between entries.
- Provide an explicit `Finish batch` action and a running count of successfully
  added books.
- Reuse the same composed create-and-place command as single-book creation.
- Barcode/ISBN multi-source enrichment remains a later scanning increment, but
  the Batch Add component must be designed so it can receive those proposals.

## 6. Implementation sequence

### Increment A — safe presentation data

Implementation status: complete.

1. Add the membership-summary projection and authorization tests.
2. Derive selected perspective labels and true query/filter-active state in
   pure helpers with frontend tests.
3. Do not alter existing dashboard layout yet.

Acceptance: Owner and both Viewer scopes receive only permitted display data;
outsiders receive no library existence signal.

### Increment B — compact shell

Implementation status: complete and accepted on desktop and mobile.

1. Replace the welcome block and three control buttons with the four compact
   controls: library, view/perspective, user/session, and Settings.
2. Move library selection/create/join into the library popover.
3. Move Members & Invitations and Customize Layout into Settings.
4. Preserve full-screen Library Map behavior and responsive popover bounds.

Acceptance: desktop, narrow phone, tablet, orientation changes, keyboard focus,
outside-click/Escape closure, and no inaccessible menu behind the map.

### Increment C — catalogue heading

Implementation status: complete and accepted on desktop and mobile.

1. Add the compact icon/eyebrow/title/count block.
2. Add Private/Shared wording and the safe member summary.
3. Add perspective-aware ownership wording and accurate filtered count text.

Acceptance: self, other-Owner perspective, catalogue-only Viewer, map Viewer,
single-member library, shared library, and active/cleared filters.

### Increment D — create/edit placement

Implementation status: complete. Add and Edit use composed atomic metadata and
placement endpoints; the separate row action has been removed.

1. Extract one reusable physical-location field group.
2. Introduce the composed, atomic create/update placement service contract.
3. Integrate it into Add/Edit Book and remove the separate row action.
4. Test collision insertion, source compaction, no-location choice, stale
   hierarchy references, authorization, and transaction rollback.

Acceptance: add directly into an empty, occupied, and final position; edit
within and across containers; remove location; test on phone.

### Increment E — Batch Add

Implementation status: complete and accepted. The iterative
editor reports its saved count, retains the container, proposes the following
position, and exposes `Finish batch` explicitly.

1. Build the iterative dialog from the same Book Editor primitives.
2. Retain destination, advance proposed position, and reset book-specific data.
3. Add clear progress, failure recovery, cancel/finish behavior, and tests.

Acceptance: add several books consecutively to one container, insert one in the
middle, change destination mid-batch, reject an invalid record without losing
previous additions, and finish cleanly on desktop/mobile.

## 7. Verification and Git gates

For every increment:

- run backend tests, frontend tests, ESLint, and production build;
- verify no call available to `CATALOG_ONLY` fetches map/location data;
- inspect structured audit events for every write;
- avoid any migration unless implementation discovers a genuinely missing
  persistent field;
- manually validate desktop and mobile before commit;
- keep BOOKPILE Local and its populated SQLite database untouched.

The preferred Git strategy is to finish the accepted Phase 4D rearrangement
commit first, then implement this plan as a new focused feature branch or as
clearly separated commits after the current branch strategy is reviewed.
