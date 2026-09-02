# BOOKPILE physical-geometry implementation plan

Status: implementation in progress on `feature/server-physical-geometry`.

This document is the canonical specification for combining measured physical
dimensions with BOOKPILE's editable visual layout. Implementation begins in
Server. A later Local release may receive a controlled backport; the populated
Local installation is never a development or migration target.

## 1. Product decisions

- Store measurements as positive integer millimetres. The initial UI uses
  millimetres only.
- A library has one shared canonical geometry, not separate manual and
  physical maps. All Owners edit it and Viewers see the same projection.
- The library has an Owner-controlled `geometry_mode`:
  - `MANUAL`: dimensions are informative and users edit geometry directly.
  - `PHYSICAL`: measured dimensions recalculate the same canonical geometry;
    missing measurements use explicit estimated/manual fallbacks.
- Switching from `PHYSICAL` to `MANUAL` freezes the latest calculated
  geometry. `Refresh proportions from physical dimensions` is an explicit
  repair/recalculation command, not an everyday requirement.
- A physical inconsistency normally saves the truthful metadata and returns a
  visible warning. A technical failure or broken relational invariant rolls
  back the entire transaction.

## 2. Coordinate system

Top-level furniture uses an unbounded world measured in millimetres:

- `x`: left edge;
- `floor_y`: baseline on which the furniture stands;
- `width` and `height`: outer dimensions;
- rendered top edge: `floor_y - height`.

Different `floor_y` values preserve the existing ability to imply depth.
Consequently, `x=500`, `width=400`, followed by `x=900` means touching
furniture; placing the second item at `x=1300` leaves a 400 mm gap.

Existing abstract Server layouts will be migrated without changing their
appearance using one old world unit = 20 mm:

```text
x_mm       = old_x * 20
width_mm   = old_width * 20
height_mm  = old_height * 20
floor_y_mm = (old_y + old_height) * 20
```

The migration is additive/reversible where practical, rehearsed on disposable
PostgreSQL, and checked before consolidation. A coordinate-system version
prevents later code from guessing which interpretation applies.

## 3. Furniture and shelves

- Known furniture `width_mm` and `height_mm` define its front-view aspect and
  world size. Depth remains useful metadata but does not directly resize the
  front view.
- Mixed measured/unmeasured furniture is allowed. Unmeasured items preserve
  manual proportions and use the median scale of measured furniture when a
  world conversion is needed; they are marked as estimated.
- Shelf `usable_width_mm` defines its internal horizontal scale.
- Shelf `usable_height_mm` determines `height_weight` when sufficient
  measurements exist. Remaining outer furniture space is distributed as
  boards and frame. Missing values retain manual weights or use an even
  fallback.
- A sum of usable dimensions that exceeds the furniture is an immediate
  physical warning, not an excuse to discard the measurements.
- Resizing furniture directly in `PHYSICAL` mode edits millimetres and shows
  the live mm value. In `MANUAL` mode it edits presentation geometry only.

## 4. Books and fallbacks

Book dimensions mean:

- `height_mm`: spine length;
- `width_mm`: front-cover width;
- `thickness_mm`: spine thickness.

Each axis is independently nullable. Rendering fallbacks are evaluated per
axis:

1. measured value;
2. for thickness, pages multiplied by the catalogue's median measured
   thickness-per-page ratio;
3. median known value for that axis;
4. final defaults: 20 mm thickness, 220 mm height, 150 mm width.

Zero and invalid values are treated as unknown. Measurements over 2000 mm or
over 50% of a non-empty assigned container produce a confirmable warning.

ROW geometry uses the sum of book thicknesses as occupied width and the
tallest book as height. Books are bottom-aligned, giving naturally stepped
tops. PILE geometry uses summed thickness as height and the longest rotated
book as width. Initial PILE alignment is `RIGHT`; `LEFT`, `CENTER`, and later
fine offsets remain extensible options.

## 5. Containers and accordion behaviour

Containers do not need stored physical dimensions. Their occupied physical
size is derived from books and their shelf:

```text
ROW width  = sum(thickness) / shelf usable width
ROW height = max(book height) / shelf usable height
PILE width = max(book height) / shelf usable width
PILE height= sum(thickness) / shelf usable height
```

The resulting percentages update the existing canonical container geometry.
The transverse axis remains unchanged unless explicitly edited.

When a container grows, preserve its anchor and recursively move neighbouring
containers in the growth direction when they have room. Only containers in
the same shelf layer constrain one another; foreground and background do not
push each other. When movement cannot satisfy the required size, render the
truthful occupied size even if it overlaps or exits the shelf and apply an
immediate translucent red warning with a tooltip. Shrinkage leaves physical
free space rather than stretching the remaining books.

Physical warnings visible in the normal map include out-of-shelf geometry,
same-layer collision, missing support, impossible internal dimensions,
accidental furniture overlap, and oversized items. A later data-review mode
may additionally expose estimated or suspicious measurements.

## 6. Supports

The existing pile-only support representation becomes a generic, acyclic
same-shelf/same-layer support graph:

- `support_kind`: `SHELF` or `CONTAINER`;
- nullable `support_container_id`;
- allowed initially: ROW on shelf, ROW on PILE, PILE on shelf, PILE on ROW;
- rejected: ROW on ROW, PILE on PILE, empty-container support, cross-layer or
  cross-shelf support, and cycles.

Dependants recalculate when their support moves or changes size. A PILE on a
stepped ROW is initially horizontal at the tallest relevant contact, possibly
leaving a visible gap. A later enhancement may compute the upper envelope,
two contact points, tilt angle, rotated hitboxes, and collisions. That realistic
two-contact tilt requires no new persisted measurement but is deliberately
deferred because it substantially complicates rendering and interaction.

## 7. Persistence and derived diagnostics

Existing dimension, hierarchy, layout-revision, row-anchor, placement, and
visual-layout data remain useful. Server needs a backed-up migration adding or
clarifying:

- library/layout `geometry_mode` (`MANUAL` or `PHYSICAL`);
- `coordinate_system_version`;
- explicit `floor_y` semantics;
- generic container support fields;
- `pile_alignment` (`LEFT`, `CENTER`, `RIGHT`).

Measurement source and physical violations are normally derived, not stored.
Map/layout responses can include structured diagnostics with entity, severity,
kind, and message. This avoids stale warning rows after metadata changes.

A physical-mode write is one transaction: update measurements, recalculate
affected containers, run accordion movement, recalculate support dependants,
detect violations, and persist the book/furniture plus canonical geometry.
Optimistic layout revisions and library-scoped PostgreSQL locks prevent stale
or cross-Owner writes.

## 8. Editing and rearrangement are separate workflows

`Edit layout` manages furniture, shelves, containers, anchors, supports, and
alignment. Its precise controls will live in a floating, minimizable map panel;
direct drag/resize is an additional interface over the same validation service.

`Reorganize books` moves physical copies between positions and containers. It
must port Local's squeeze, swap, continue, collapse, leave-gap, preview,
multi-move chain, and atomic Apply semantics into library-scoped PostgreSQL.
Provisional geometry is frozen while a chain is being composed, recalculated
on Apply, and fully rolled back on failure.

## 9. Server implementation order

1. Restore location presentation in catalogue rows and per-book placement;
   remove the temporary global `Position books` form.
2. Port visual `Reorganize books` into Library Map using the existing tested
   Local algorithms behind Server authorization and transactions.
3. Back up and migrate Server for the geometry mode, coordinate version,
   generic supports, and PILE alignment.
4. Implement and test the pure physical-geometry/accordion engine and its
   structured warnings.
5. Integrate the precise editor as a floating/minimizable map panel.
6. Add direct layout manipulation over the same service.
7. Validate desktop, phone, and tablet behaviour before closing Phase 4D.

### Implementation record

Accepted on 2026-09-02:

- A verified PostgreSQL and private-object backup preceded the reversible
  schema-v9 rehearsal and live migration.
- Schema v9 stores `MANUAL`/`PHYSICAL`, coordinate-system version 2,
  millimetre furniture/outside-area geometry, generic acyclic supports, row
  anchors, and PILE alignment. Existing catalogue and layout records were
  preserved.
- The editor exposes millimetres only. Container positions are internally
  converted to compatible canonical percentages: anchor/alignment position is
  measured from the shelf's left edge, while bottom clearance is relative to
  the immediate support and zero means physical contact.
- Background containers resting on a shelf may retain a visual depth offset;
  foreground or container-supported geometry cannot float.
- Per-axis book fallbacks are implemented and tested: measured value,
  page-derived thickness where possible, catalogue median, then 20/220/150 mm
  defaults.
- `MANUAL` rendering remains isolated from physical projection, preventing
  partial physical data from changing an existing manual map. Wheel zoom no
  longer has a fixed world-width ceiling.

Still required before Phase 4D closes: complete physical-mode projection,
accordion movement, structured warning overlays, floating/direct layout
editing, and final cross-device acceptance.

## 10. Edition boundary and future Local work

Server receives this implementation first because it already stores dimensions
and its physical-map architecture is under active development. No change is
made directly to `C:\Users\Russula\.code\_PERSONAL_LIBRARY_MANAGER`.

A future Local release will use a separate branch/worktree, a fresh verified
ZIP restored into isolated acceptance data, and an additive SQLite migration.
Candidate backports include row anchors and supports in the UI, the shared
manual/physical geometry semantics, millimetre editing, physical warnings,
accordion behaviour, generic supports, PILE alignment, and eventually the
two-contact tilted PILE renderer. Local's stable v1.0.0 artefacts remain
immutable and older ZIPs remain supported.
