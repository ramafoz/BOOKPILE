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
- A shelf is an explicit rectangular usable compartment inside its furniture,
  not a proportional share of the other shelves. Its canonical map geometry
  therefore requires a furniture-relative horizontal coordinate, floor
  baseline, width and height. In `PHYSICAL` mode, recorded
  `usable_width_mm`/`usable_height_mm` determine that rectangle's size. For
  example, a 200 mm shelf in 1000 mm furniture occupies exactly one fifth of
  its height; unused space remains visibly solid furniture rather than being
  redistributed among shelves.
- Shelf horizontal alignment is `LEFT`, `CENTER` (default), or `RIGHT`, with a
  signed millimetre offset from the selected alignment. Vertical coordinates
  use the same positive-up floor-baseline convention as furniture.
- Shelves are always fully contained by their furniture and never overlap.
  These are hard relational invariants: a shelf edit or furniture resize that
  violates them must be rejected rather than stored as a warning.
- Furniture has a configurable default shelf-numbering/placement direction:
  `TOP_TO_BOTTOM` (default), `BOTTOM_TO_TOP`, `LEFT_TO_RIGHT`, or
  `RIGHT_TO_LEFT`. This supports both conventional tall bookcases and wide
  furniture divided into vertical compartments. Shelf number remains an
  identifier/order; explicit geometry becomes authoritative after placement.
- `usable_depth_mm` remains metadata for capacity and future depth rendering;
  it does not alter the initial front-view rectangle.
- A sum of usable dimensions that exceeds the furniture is an immediate
  hard conflict when it causes shelf overlap or escape from the furniture.
- Resizing furniture directly in `PHYSICAL` mode edits millimetres and shows
  the live mm value. In `MANUAL` mode it edits presentation geometry only.

### Canonical shelf, frame, and separator model

Furniture measurements are exterior dimensions. Their independent fallbacks
are 2200 mm high, 800 mm wide, and 280 mm deep. Shelf measurements are the
interior usable dimensions of a compartment. Every value exposed by the
editor identifies both its unit and its source: `ENTERED`, `FALLBACK`, or
`DERIVED`. Manual furniture geometry still uses millimetre-shaped world units,
but labels them as fictitious unless recorded physical dimensions make them
real. There is only one canonical map; no parallel manual and physical maps
may drift apart.

Each furniture item has an immutable distribution direction once physical
structure exists: `TOP_TO_BOTTOM`, `BOTTOM_TO_TOP`, `LEFT_TO_RIGHT`, or
`RIGHT_TO_LEFT`. The UI uses those full names. A direction change is allowed
only before shelves and containers exist. Shelf numbering follows that
direction, while every shelf has an explicit, furniture-relative rectangle.

Fallback shelf dimensions are preferred dimensions, not sibling weights:

- vertical distribution: 14% of furniture height, 95% of its width when the
  default 2.5% frame is present on both sides, and
  99.75% of its depth;
- horizontal distribution: the height remaining after the upper closure and
  lower board, 14% of its width, and
  99.75% of its depth.

If preferred fallback compartments do not fit, fallback-only dimensions are
compressed equally and proportionally, never below 5 mm. Entered dimensions
are never compressed. A structure that still cannot fit is rejected.

For vertical furniture, each compartment may have its own left and right
frame. The furniture also has upper and lower closures and horizontal
separators between consecutive shelves. Residual space follows the numbering
direction: it is absorbed by the lower closure for top-to-bottom furniture and
by the upper closure for bottom-to-top furniture. For horizontal furniture,
each compartment may have its own upper closure and lower board; vertical
separators divide consecutive shelves. Residual width is shared equally by
separators, or by the two outside frames when there are no separators. If one
outside frame is zero, the other receives all residual space; if neither
exists, the shelf spans the furniture.

Every non-zero frame, closure, board, separator, or compartment dimension is
at least 5 mm. Separators have no free offset: a partial separator touches its
selected top or bottom anchor. In horizontal furniture, a zero upper closure
causes homogeneous separators to use 50% height; otherwise they use full
height.

`Homogeneous structure` is enabled by default. In vertical furniture it keeps
left/right frames equal and all separator thicknesses equal. In horizontal
furniture it equalizes lower boards plus separator thickness, height, and
bottom anchoring. Enabling it previews and confirms any destructive visual
normalization; disabling it preserves the current values and permits
per-shelf asymmetry, including zigzag/S-shaped compartments.

Only the physically uppermost compartment may be marked `Open top shelf`.
That removes its upper closure and side frames. It cannot be enabled when an
entered shelf width is incompatible with the furniture width; an explicitly
full-width top shelf is valid. Other shelves require their containing frame.

Shelves never overlap or escape furniture. New shelves are placed atomically
at the end of the numbering direction with their separator and preferred
fallbacks; they are not created if no valid fit exists. Furniture resizing,
mode changes, entered-dimension changes, and homogeneity changes use preview
and confirmation whenever they displace geometry. Invalid previews cannot be
applied. `PHYSICAL` to `MANUAL` freezes the calculated rectangles as editable
percentages; `MANUAL` to `PHYSICAL` previews the entered/fallback physical
projection before replacing derived geometry.

Depth is stored and must not exceed furniture depth, but it does not yet alter
the front-view renderer. In `MANUAL`, shelf and container controls use clearly
labelled percentages relative to their parent. In `PHYSICAL`, they use clearly
labelled millimetres and entered physical dimensions remain read-only wherever
the visual value is derived from them.

The current `height_weight` implementation is transitional. It must be
replaced by an additive, backed-up migration to explicit shelf rectangles and
structural settings, preserving the pre-migration appearance before physical
projection is adopted.

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
- Physical projection is implemented for non-empty ROW/PILE containers. Their
  occupied width and height are derived from per-axis book measurements and
  documented fallbacks; the precise editor therefore locks those two derived
  fields in `PHYSICAL` mode while retaining editable anchors, alignment and
  support. Empty containers retain editable provisional geometry.
- Schema v10 removes obsolete `0–100` persistence bounds and widens the four
  container geometry numerics. This allows truthful physical overflow while
  retaining positive width/height constraints and immediate red diagnostic
  overlays. The migration was backed up and rehearsed upgrade/downgrade/upgrade
  against disposable PostgreSQL before application.
- Top-level vertical coordinates now consistently use a mathematical axis:
  `floor_y=0` is below `floor_y=1800`. Furniture, Reading and On-loan areas all
  use left edge, floor baseline, width and height semantics.
- Newly created unmeasured furniture keeps null physical metadata, receives a
  distinct persisted fallback map rectangle, and accepts negative horizontal
  world coordinates without transient number-input correction.
- Schema v11 adds explicit shelf rectangles plus furniture direction,
  frame/closure/separator settings and per-shelf source, alignment, offset,
  open-top and non-homogeneous structure fields. The PostgreSQL migration was
  backed up, rehearsed through upgrade/downgrade/upgrade, then applied without
  changing the 15 books, 2 shelves, 4 containers or private cover objects.
- Existing shelf appearance is backfilled from the previous normalized
  geometry. The renderer also retains a defensive legacy fallback so a rolling
  frontend/backend restart cannot hide shelves or crash the editor.
- Acceptance confirmed preservation, no-op saves, MANUAL percentage controls,
  PHYSICAL recalculation, absolute shelf height, derived-field locking,
  atomic rejection of a shelf that cannot fit, and immutable distribution
  direction once a shelf exists.

The schema-v11 structural-control checkpoint is now accepted. Independent
per-shelf controls are revealed only when homogeneity is disabled; restoring
homogeneity warns before recalculation. The checkboxes are compact and the
exceptional alignment offset lives under an explicit advanced disclosure.
Furniture direction and initial homogeneity can be chosen when empty furniture
is created, while direction remains immutable after its first shelf.

Editor selection now cascades from furniture to shelf to container, so empty
furniture cannot expose another furniture's containers. Independent controls
also follow the distribution axis: vertical furniture shares upper/lower
closures and exposes per-shelf side frames, while horizontal furniture shares
side frames and exposes per-shelf upper/lower boards. Outside-library area
controls are explicitly labelled in millimetres.

Still required before Phase 4D closes: add floating/minimizable and direct map
layout editing, refine deeper accordion edge cases, and complete final
cross-device acceptance.

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
