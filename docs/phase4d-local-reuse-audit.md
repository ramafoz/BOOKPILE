# Phase 4D Local-to-Server reuse audit

Status: implementation guide for `feature/server-physical-map`.

## Purpose

BOOKPILE Server must preserve the validated behaviour and visual identity of
BOOKPILE Local without copying its single-user persistence and authorization
assumptions. The populated Local worktree is a read-only reference during this
phase and is never a Server test target.

## Reuse classification

| Local capability | Server treatment | Reason |
| --- | --- | --- |
| `mapCamera.ts` camera mathematics | Port as a pure frontend module with its tests | It has no API, database, or user coupling. |
| `mapInspection.ts` selection toggle | Port directly with UUID-compatible types | It is pure selection state. |
| `mapBookGeometry.ts` page proportionality and outside-area layout | Port with Server book projections | The formulae are edition independent. |
| `visual_geometry.py` | Port pure rules and tests, changing integer IDs to UUID-compatible generic identifiers | Geometry has no persistence dependency. |
| `rearrangement_geometry.py` | Defer to the rearrangement increment, then port the tested algorithm | It is reusable, but must run inside a PostgreSQL transaction with library-scoped locks. |
| Library Map visual hierarchy and product styling | Recreate as smaller Server components while retaining Local visual tokens and interaction semantics | Local's implementation is embedded in a very large `App.tsx`. Copying it whole would preserve unwanted application state coupling. |
| Layout update validation | Port rules into a Server service and add tenant/isolation checks | Local validates one implicit library; Server must validate every referenced UUID against one authorized library. |
| Book position and collision behaviour | Port semantics and regression cases | Server requires atomic concurrency-safe writes rather than SQLite-global operations. |
| SQLite queries, backup paths, cover paths, reading status projections | Do not copy | These are edition-specific or personal-data assumptions. |

## Confirmed Local frontend gap

Local schema v8 and its backend already store and validate:

- `row_anchor`: `LEFT` or `RIGHT`;
- `pile_support_kind`: `SHELF` or `ROW`;
- `pile_support_container_id` for row-supported piles.

The current Local Edit Layout panel exposes only container start, width,
vertical position, and height. It does not expose row anchor or pile support.
Server must not inherit this omission. Its editor will provide:

- a row growth anchor selector for every row;
- an explicit shelf/row support selector for every pile;
- only non-empty rows in the same shelf and layer as support candidates;
- a clear validation error when a pile has no valid support.

A future Local release may backport these controls on a separate Local branch,
after backup and isolated acceptance testing. Phase 4D never changes the live
Local worktree.

These items are now tracked explicitly in `TODO.md`. Any additional parity
improvement discovered while building Server must be added to that controlled
backport list; discovery never authorizes a direct edit of the populated Local
installation.

## Phase 4D parity gates

Before Phase 4D can close, Server must provide:

1. Complete library-scoped hierarchy and geometry serialization.
2. Owner-only hierarchy and layout writes; map-capable Viewer read access;
   catalogue-only Viewer denial.
3. Explicit row anchors and pile supports in both API and editor.
4. Same-layer non-overlap and cross-layer depth-overlap limits.
5. Unbounded furniture/outside-area coordinates with finite positive sizes.
6. Responsive camera navigation and inspection derived from Local's pure
   modules.
7. Page-proportional book rendering with the Local fallback mean and 200-page
   final fallback.
8. Automated isolation, geometry, API, and frontend tests plus desktop/mobile
   acceptance.

The hierarchy, precise editor, responsive camera, proportional renderer,
desktop/mobile navigation, pinch gesture, and book/container inspection gates
were accepted on 2026-09-01. The next parity increment now also implements:

1. Local's established location UX in Server catalogue rows and per-book
   editing, replacing the temporary global `Position books` form.
2. Visual rearrangement with movement modes selected before the first move,
   multi-step Continue chains, multiple completed operations in one draft,
   retained-gap validation, proportional container resizing, undo, and an
   explicit atomic Apply.
3. Owner-only preview/apply APIs scoped to one library. Preview is read-only;
   Apply locks the library, repeats validation, rejects stale revisions, writes
   positions and visual geometry in one transaction, and records an audit
   event.

The placement and rearrangement increment passed desktop and responsive manual
acceptance on 2026-09-02, including same/cross-container moves, all movement
modes, multi-operation drafts, undo, persistent-gap rejection, proportional
geometry, selectable retained and end positions, and the collapsible draft
panel.

The schema-v9 physical-geometry foundation, generic support rules, per-axis
fallback engine, millimetre-only precise editor, and strict manual/physical
rendering boundary were accepted on 2026-09-02. The remaining Phase 4D work is
complete physical projection, accordion/warning behaviour, and floating/direct
layout editing through the full model in `../PHYSICAL_GEOMETRY_PLAN.md`. Automated gates now
cover the pure movement engine, read-only preview, stale-revision rejection,
atomic application, authorization, and existing geometry rules.

The physical model is Server-first. Its reusable pure geometry rules and UI
improvements are candidates for a later controlled Local backport, but neither
Phase 4D nor its tests may write to the populated Local worktree.
