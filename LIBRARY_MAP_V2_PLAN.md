# Library Map v2 — viewport, navigation, and inspection plan

Status: **implementation in progress** on `feature/library-map-viewport`.
Phases 1 and 2 are implemented and manually accepted; phase 3 is next.

No catalogue or layout data should be rewritten merely by opening the new map.
Any persistent-layout change must continue to require explicit layout-editing
and Save actions.

## 1. Product goals

- Replace the fixed `0–100` room canvas with an effectively unbounded visual
  world.
- Keep the visible viewport finite and responsive to desktop, tablet, and phone
  dimensions.
- Navigate the viewport with directional controls, zoom controls, reset, and
  target-focused views.
- Present the map as a full-device application surface with an explicit route
  back to the catalogue.
- Inspect either one book or one container without leaving the map.
- Open the main catalogue with the exact selected book or container filter only
  when the user explicitly requests it.
- Give each book a visual thickness proportional to its page count while
  preserving the user-defined total container size.
- Preserve all existing colour modes, overlapping foreground/background
  behaviour, layout editing, visual rearrangement, Reading area, and On-loan
  area.

## 2. Core model: world, viewport, and screen

The implementation must keep three concepts separate:

1. **World coordinates** are persistent. Furniture, Reading, and On-loan areas
   live here and may be placed at negative or positive coordinates without a
   room boundary.
2. **Viewport/camera state** is temporary. It contains a world-space centre and
   zoom level and determines which part of the world is visible.
3. **Screen coordinates** depend on the current device and are calculated from
   the camera. Resizing or rotating a device must not move furniture in world
   coordinates.

Shelf proportions and container rectangles remain local to their parent
bookcase/shelf. The unbounded coordinate change applies to top-level visual
objects; it must not allow a container to escape its shelf.

The current layout uses bounded percentage coordinates. Existing values must
be mapped losslessly into the new world coordinate system. Loading the map must
not itself migrate or rewrite those values. Before implementation, decide
whether to use a permanent origin offset over the current stored coordinates or
introduce an explicit layout-coordinate version.

## 3. Interaction modes

The toolbar must expose clearly exclusive modes so a click cannot both select
and mutate data:

- **Inspect book**: clicking a book selects it without moving the camera.
- **Inspect container**: clicking a container selects it without moving the
  camera. When a background container is selected, books in obscuring
  foreground containers disappear and the foreground container shell remains
  as a 15%-opacity grey silhouette.
- **Rearrange books**: retains the existing provisional, atomic rearrangement
  workflow.
- **Edit layout**: retains explicit layout editing and Save/Cancel semantics.

Camera controls remain available in every mode unless a pointer drag is already
being used for a layout or rearrangement operation.

Selection, inspection, and camera framing are distinct actions:

- A single click/tap selects and highlights without changing zoom.
- A desktop double-click opens the compact inspector. Touch devices expose an
  explicit **Show book** or **Show books** action after selection instead of
  depending on double-tap.
- A separate **Frame selection** action centres and fits the selected target.
- A toolbar hierarchy chooser can frame a bookcase, shelf, or container.
- Selecting a shelf only highlights it; it does not open a compact catalogue.

## 4. Viewport controls

- Four directional buttons pan the camera up, down, left, and right.
- Zoom in and zoom out use the viewport centre when nothing is selected and the
  selected target when a selection exists.
- Controls support click/tap and accessible keyboard activation.
- A tap moves one step; holding a directional control pans continuously.
- Each pan step is a fixed percentage of the currently visible world span, so
  movement remains perceptually consistent at every zoom.
- Apply conservative minimum and maximum zoom limits, while always allowing a
  fit-to-target command to display its complete target.
- Recalculate screen dimensions with `ResizeObserver` and mobile viewport units
  so rotation and browser-chrome changes do not alter world coordinates.
- Direct canvas drag, mouse-wheel/trackpad zoom, and pinch-to-zoom form a later
  increment after button navigation has passed multi-device validation.

## 5. Reset and focus commands

### Reset world view

- Centre the camera horizontally on world coordinate `x = 0`.
- Calculate the vertical bounds from the highest top edge to the lowest bottom
  edge of all bookcases and the Reading and On-loan visual areas.
- Fit those vertical bounds inside the available viewport with responsive
  padding equal to 5% of the smaller viewport dimension, clamped from 16 to 48
  screen pixels.
- Let the device aspect ratio determine the visible horizontal span; distant
  furniture may therefore remain outside the screen width.
- When no bookcase exists, do not generate an empty map. Open **Customize
  library layout** with an explanation that the first bookcase must be created.

### Focus a bookcase

- Let the user choose one existing bookcase.
- Centre it horizontally and vertically.
- Fit its complete height with the same responsive padding policy; screen aspect ratio
  determines the width shown.

### Focus a shelf or container

- Derive exact world bounds from the nested bookcase, shelf weights, and local
  container rectangle.
- Fit and centre the selected target without changing persistent layout data.
- Provide an obvious route back to the world reset or parent bookcase.

## 6. Full-screen map surface

- Replace the current scrollable dialog presentation with a dedicated
  viewport-sized map surface.
- Keep controls and selection information in overlays that do not change world
  geometry.
- Add an explicit **Back to catalogue** control that closes the map and restores
  the catalogue state.
- Browser Back and `Escape` both return to the catalogue.
- Keep **Rearrange books** and **Edit layout** discoverable through one compact
  floating tools button. During increments where transformed writes are not yet
  safe, show both options as explicitly unavailable instead of hiding them or
  exposing a partially functional workflow.
- Each write mode must open its controls in a floating workspace panel above
  the map. The panel must:
  - be minimizable and restorable without losing draft state;
  - remain inside phone, tablet, and desktop safe-area bounds;
  - expose every mode selector, validation message, movement summary, and
    Apply/Save/Cancel action without requiring document scrolling;
  - leave enough of the map visible to select furniture, containers, books, and
    destinations;
  - preserve its draft while the camera pans or zooms;
  - block closing the map or changing mode when unsaved changes exist until the
    user explicitly confirms discarding them.
- Layout editing and rearrangement are not considered restored merely because
  their map gestures work. Their complete floating-panel workflows and backend
  confirmation/save paths must pass multi-device validation first.
- Use reliable CSS application fullscreen (`100dvh`) as the guaranteed
  behaviour. Native browser fullscreen is not required for this increment.
- Respect safe-area insets on notched mobile devices.

## 7. Book and container inspection

### Book mode

- Clicking a visual book selects exactly that book.
- Keep it visually emphasized while other books are subdued.
- A desktop double-click or explicit touch-friendly action opens a bottom
  inspector containing only cover, title, and author.
- Offer a button to leave the map and open the main catalogue with an exact
  book-ID filter.

### Container mode

- Clicking a container selects exactly that container.
- When a selected background container is obscured, temporarily hide books in
  only the intersecting foreground containers and leave their shells as
  transparent grey context. Restore them when selection changes or closes.
- A desktop double-click or explicit touch-friendly action opens a bottom
  compact catalogue sorted by physical position.
- Show only cover, title, and author; do not expose per-book edit, loan,
  Goodreads, delete, or other row actions.
- Offer a button to leave the map and open the main catalogue filtered by that
  container and sorted by physical position.

### Inspector presentation

- Use a responsive bottom drawer that overlays the map, can be closed, scrolls
  internally, and never extends beyond half the screen height.
- Rows expose no catalogue actions. Selecting a row only highlights that book
  on the map; it does not change mode or leave the map.
- If selecting a very thin row automatically magnifies its map segment, save
  the previous camera first and restore it exactly when that highlight or the
  inspector closes.
- An empty map click or the drawer close button clears the active selection.
- Lazy-load cover images in large containers.
- Preserve keyboard focus and screen-reader labels.

## 8. Page-proportional book thickness

Calculate one fallback page count whenever the map data changes:

1. Unrounded arithmetic mean of every positive `page_count` in the complete
   library, including books currently Reading or On loan.
2. If no positive page counts exist, use `200`.
3. A book with missing page metadata uses that fallback only for rendering; its
   stored metadata remains unchanged.

For each container:

- Let `effectivePages(book)` be the stored positive page count or fallback.
- Let `totalPages` be the sum of effective pages for all displayed books.
- In a row, allocate each book
  `containerWidth × effectivePages / totalPages` along the horizontal axis.
- In a pile, apply the same ratio to the vertical stacking axis, preserving the
  established top-to-bottom position order.
- Preserve the container's user-defined total width and height.
- Keep thin contour lines between books.
- Keep exact geometry separate from a potentially larger invisible pointer hit
  area so very thin books remain selectable without falsifying their visible
  proportions.
- Preserve strict proportionality even when a genuinely large book visually
  dominates its container. Metadata entry above 2,000 pages requires an
  explicit confirmation but remains permitted.
- If a sub-pixel book is chosen from the compact container list, automatically
  zoom until its thickness is approximately 16 screen pixels and visibly show
  its selection colour.
- A Reading or On-loan book retains a faint outlined gap and tooltip in its
  saved container. It still contributes its effective pages to that
  container's geometry, and a book that is both Reading and On loan leaves only
  one gap.
- A temporary `last position + 1` rearrangement destination reserves visible
  space with the effective thickness of the book being moved.
- Freeze the current book geometry throughout a provisional rearrangement so
  books do not expand or contract while the user builds and reviews a movement.
  After **Apply**, recalculate the source and destination containers from their
  new effective-page totals. Cancel leaves the original geometry unchanged.

### Reading and On-loan presentation

- Treat Reading and On-loan as freely positioned and resized top-level world
  objects for framing and reset calculations, while keeping them visually
  distinct from bookcases and from one another.
- Represent Reading as a table with books lying horizontally and stacking into
  additional piles automatically when required.
- Represent On-loan as an absent/out-of-library area with a soft irregular
  cloud-like boundary and vertical books that flow into additional rows when
  required.
- Preserve page-proportional visual thickness in both areas. A book without a
  retained physical container uses the global fallback geometry.

## 9. Data and compatibility strategy

- No new bibliographic fields are required; page count already exists.
- Camera state is temporary presentation state and always resets when the map
  opens; it is not stored in the database or local storage.
- Unbounded top-level coordinates require backend validation to accept finite
  negative and positive `x/y` values while retaining positive size constraints.
- Top-level objects retain practical minimum dimensions and an initial maximum
  size of 1.5 times the current limit.
- Layout editing supports both direct dragging and numeric world-coordinate
  `X/Y` fields. Infinite-position X/Y sliders are removed.
- Existing container collision and foreground-over-background rules remain
  local to a shelf.
- Existing backups already include visual-layout tables. If stored coordinate
  semantics change, rehearse the conversion against a restored copy and create
  a verified backup before applying it to the live layout.
- If an explicit coordinate-version field is necessary, it becomes a small,
  additive, rehearsed database migration; otherwise avoid a schema migration.
- The catalogue database and cover files must never be copied into Git or the
  feature branch.

## 10. Implementation roadmap

### Phase 0 — specification and safety baseline

- Resolve every open decision in this document.
- Record current desktop, tablet, and phone behaviour with screenshots.
- Add pure geometry tests for world/screen transforms and nested target bounds.
- Decide whether coordinate-version persistence is required.
- Create and validate a full ZIP backup before the first test that saves an
  unbounded layout.

### Phase 1 — camera over the existing map — complete

- Introduce world-to-screen transform helpers and camera state.
- Render the current layout unchanged through the camera abstraction.
- Add responsive full-screen surface, exit control, arrows, zoom, and world
  reset.
- Keep layout editing and rearrangement temporarily disabled if necessary until
  their transformed pointer coordinates are safe.
- Validate desktop, tablet, portrait phone, landscape phone, and rotation.

### Phase 2 — unbounded top-level layout — complete

- Remove `0–100` top-level position bounds from frontend interaction and backend
  validation while retaining finite-number and positive-size checks.
- Replace bounded X/Y sliders with suitable numeric/direct manipulation tools.
- Convert screen pointer deltas into world deltas at every zoom level.
- Include Reading and On-loan areas in the same world model.
- Build the reusable floating, minimizable workspace-panel shell and migrate
  the complete layout editor into it, including precise controls,
  collision/errors, Save, and Cancel.
- Verify Save/Cancel and backup round trips before enabling editing by default.

Implementation record: schema v7 losslessly shifted legacy top-level X
coordinates by `-50`, making world coordinate `x = 0` the reset centre without
changing the relative layout. The migration was rehearsed against a validated
v6 ZIP and then applied to the live catalogue with 434 books preserved,
successful integrity and foreign-key checks, and verified pre/post backups.

### Phase 3 — target focus — complete

- Add world reset, bookcase chooser, and fit-to-bookcase.
- Add shelf and container bounds calculation and fit commands.
- Verify padding and centring at extreme aspect ratios and coordinate values.

Implemented with adaptive-resolution rendering so close shelf/container focus
remains sharp instead of magnifying a previously rasterized map layer.

### Phase 4 — inspection modes — complete

- Add explicit Book/Container selection mode.
- Add selected-book highlighting and compact inspector.
- Add selected-container isolation and compact position-sorted catalogue.
- Add explicit transitions from the inspector to exact catalogue filters.
- Keep all inspectors read-only.

Implemented with mutually exclusive Book/Container modes, overlap-aware
background isolation, compact position-sorted inspectors, reversible
full-screen complete book information, and exact catalogue exits that keep the
advanced-search panel collapsed. The map API only gained existing cover data
and a read-only single-book endpoint; no catalogue schema or records changed.

### Phase 5 — page-proportional rendering — complete

- [x] Add tested effective-page and proportional-segment calculations.
- [x] Render row widths and pile heights from effective page counts.
- [x] Add accessible hit areas for tiny segments.
- [x] Confirm colour modes remain independent from geometry.

Implemented after a rehearsed and verified v7-to-v8 migration that stores row
anchors and explicit pile supports. The populated catalogue retained all 434
books and covers, and the live layout now records 18 shelf-supported and 9
row-supported piles without changing bibliographic or physical-position data.
Missing page counts use the arithmetic mean across the complete catalogue.

### Phase 6 — integration hardening

- Integrate projected page-proportional container geometry and destination
  slots into provisional rearrangement chains.
- Restore transformed layout handles and pointer drag at arbitrary zoom.
- Restore visual book rearrangement at arbitrary camera positions and zoom.
- Migrate all rearrangement modes, position controls, movement-chain summaries,
  gap/conflict validation, Undo, Apply, and Cancel into the floating,
  minimizable workspace panel. A minimized rearrangement must retain the full
  provisional chain unchanged.
- Test overlapping containers, Reading, On-loan priority, focused-book entry,
  and all exit/filter paths.
- Add frontend tests for camera math, selection state, and proportional books;
  add backend tests for unbounded finite coordinates and invalid geometry.

### Phase 7 — multi-device acceptance and merge

- User validation on desktop browser, phone, and tablet.
- Test narrow/short screens, orientation changes, browser zoom, and touch.
- Confirm no catalogue, cover, reading-session, loan, or physical-position data
  changes merely from inspection/navigation.
- Update README and TODO, run the complete test/build suite, then merge the
  feature branch into `main` only after explicit approval.

## 11. Risk register

- **Coordinate compatibility:** blindly reinterpreting current `0–100` values
  could move every piece of furniture. Mitigation: reversible transform or
  versioned conversion, tested against a backup.
- **Pointer math:** layout drag and book rearrangement currently use screen
  percentages. Pan/zoom requires inverse transforms; a mistake could select or
  move the wrong destination. Mitigation: pure transform tests and phased
  re-enablement.
- **Mode conflicts:** select, focus, edit, and rearrange clicks can compete.
  Mitigation: explicit exclusive modes and disabled incompatible actions.
- **Mobile fullscreen:** browser chrome, safe areas, and iPhone fullscreen
  support differ. Mitigation: CSS application fullscreen as the guaranteed
  baseline and native fullscreen only as progressive enhancement.
- **Inspector obstruction:** a bottom drawer can cover the selected shelf.
  Mitigation: fit against the unobscured viewport or automatically pan the
  selection above an overlay.
- **Overlapping layers:** hiding the wrong layer can remove context or hide the
  selected container itself. Mitigation: define exact z/layer rules before
  implementation and provide a one-click restore.
- **Very thin books:** strict page proportionality can produce sub-pixel books
  that are difficult to see or select. Mitigation: exact visible geometry plus
  enlarged hit areas and sensible extreme-value handling.
- **Metadata outliers:** a very large page count can visually compress every
  other book in one container. Mitigation: preserve strict visible
  proportionality, require confirmation above 2,000 entered pages, enlarge
  invisible hit targets, and temporarily magnify a selected sub-pixel book.
- **Performance:** repeated transforms, cover rendering, and hundreds of
  pointer targets can affect phones. Mitigation: transform one world layer,
  memoize geometry, lazy-load covers, and test on real devices.
- **Persisted camera state:** sharing one camera through the database would be
  wrong for different screens. Mitigation: keep all camera state temporary and
  reset it whenever the map opens.

## 12. Resolved final geometry decisions

The product specification is now closed for the first implementation cycle.
The final two geometry decisions are recorded here for traceability.

### A. Container normalization after a cross-container move

The original proportional formula makes every occupied container total exactly
100% of its user-defined stacking axis. Consequently, removing or adding a book
changes `totalPages` and causes the other books in that container to expand or
contract. Freezing book thickness avoids that visual jump, but then the books
will no longer necessarily fill the complete container.

**Decision:** freeze geometry only throughout the provisional rearrangement.
After **Apply**, recalculate the source and destination containers from their
new page totals. Do not introduce a global pages-to-world-unit scale.

For a cross-container **Swap**, compare the two exchanged books' effective-page
widths and recalculate both affected containers after **Apply**. Equal-width
books leave their relative container geometry unchanged; unequal-width books
must update both containers from their resulting page totals. No provisional
move may silently resize either container before confirmation.

### B. Camera restoration after magnifying a sub-pixel book

Selecting a very thin book from the compact inspector will automatically zoom
until its segment is approximately 16 screen pixels thick.

**Decision:** save the camera before automatic magnification and restore that
exact state when the book highlight or inspector closes.

## 13. Phase 5 geometry contract

These rules are the approved contract for proportional rendering and the
later rearrangement integration. They must be implemented as pure, tested
geometry before any schema or live-layout write is enabled.

### Axes, anchors, and support

- A `ROW` stacks books horizontally. Its height never changes automatically.
- A `PILE` stacks books vertically. Its width never changes automatically.
- Every existing and newly created row initially uses a `LEFT` anchor. A later
  layout edit may select `RIGHT`; numbering remains left to right either way.
- A pile grows upward and shrinks upward: its bottom edge remains fixed while
  `y` and `height` change by opposite amounts.
- Every pile must explicitly rest on either the shelf bottom or a non-empty row
  in the same shelf and layer. Piles cannot support piles.
- Shrinking or moving a supporting row so that horizontal support is lost
  invalidates the complete operation. An empty row cannot support a pile.
- Same-layer containers constrain growth only when their intervals overlap on
  the transverse axis. Background and foreground containers do not constrain
  one another.
- Foreground may obscure at most 80% of a background container's height; this
  limit concerns vertical coverage, not overlap area. At least 20% remains
  visible.

### Page scale and capacity

- Book thickness is strictly proportional to effective pages within its own
  container. There is no global page scale.
- Missing, zero, or invalid pages use the arithmetic mean of valid catalogue
  page counts, falling back to 200 when no valid value exists.
- Editing page metadata redistributes books inside the existing outer
  container size; it never resizes that container.
- A page edit above 2,000 pages, or above 50% of the final effective pages of a
  non-empty container, requires a warning but remains user-confirmable.
- A container may compress at most 5%: natural span up to 105% of available
  capacity is redistributed into 100%; anything larger is invalid.
- Geometry at or within 0.1 percentage points of its available capacity counts
  as full.
- An occupied full container whose pages fall by at most 5% remains full unless
  the relevant move explicitly requests `Release shelf space`. A larger
  reduction shrinks it.
- `Release shelf space` is movement-local and takes effect in sequence. Once a
  move releases a container, later moves in the same provisional chain evaluate
  that container as partial. A zero net reduction still produces no shrink.
- Empty containers visually expose their full available stacking capacity but
  do not provide physical support. They are available as rearrangement targets
  and omitted from normal container inspection.

### Cross-container movement and provisional chains

- Internal reordering changes order only. Container dimensions and current
  book thicknesses remain unchanged.
- Provisional movement freezes current book thicknesses and displays the
  projected container boundary and destination slot. Apply recalculates all
  affected books and containers.
- Cross-container moves use each container's local scale. An initially empty
  destination infers scale from occupied containers in the same shelf, then
  furniture, then the whole visual library. If none exists, the first book is
  proposed at 10% of available span with a warning to adjust it to reality.
- A full destination accepts incoming pages only if the final chain removes
  enough pages or the result fits within the 5% compression allowance.
- Swap recalculates both affected containers because equal page counts are not
  assumed.
- Final validation is atomic: one invalid container invalidates the entire
  chain. Persist book positions and affected layout geometry together or write
  nothing.

### Migration sequence

1. Run a read-only audit that infers current pile support and reports every
   ambiguity. Use the normal 0.1-point geometry tolerance for future data and a
   separately documented 3-point legacy inference tolerance for small gaps
   introduced by the existing manual layout editor; always report the original
   coordinates and never silently repair them during the audit.
2. Implement and test pure geometry calculations without database writes.
3. Create and verify a full ZIP backup and rehearse the additive v7-to-v8
   migration on an isolated copy.
4. Add `row_anchor`, `pile_support_kind`, and nullable
   `pile_support_container_id`; initially set all rows to `LEFT` and persist
   only unambiguous same-layer pile support.
5. Re-run row counts, foreign-key checks, integrity checks, support validation,
   and backup validation before touching the live database.
6. Render page-proportional books using the migrated layout, then obtain
   desktop and mobile validation before reconnecting rearrangement writes.
