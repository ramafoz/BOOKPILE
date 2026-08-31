# ADR 0008: Shared catalogue and physical hierarchy schema

- Status: Accepted
- Date: 2026-08-31
- Applies to: BOOKPILE Server Phase 4A

## Context

BOOKPILE Server must store the catalogue and physical layout shared by all
Owners without copying Local's implicit single-reader assumptions. It must
also prevent a future programming error from linking a record in one library
to a parent in another library.

The schema must accept the existing minimal Phase 1 books, preserve legacy
Title/Author display text, support extensible contributor credits, and leave
room for optional real-world measurements. Covers, personal reading sessions,
loans, and Local ZIP consolidation are separate later phases.

## Decision

1. A `book` represents one physical copy. Work/Edition/Copy normalization is
   not introduced in this phase.
2. Shared bibliographic and copy metadata live on the library-scoped book.
   Reading status and dates do not: Server will derive those from the selected
   Owner's personal sessions in Phase 5.
3. `bookcases`, `shelves`, `containers`, books, contributors, and visual layout
   carry `library_id` or an equivalent unambiguous library path.
4. Parent relationships use composite foreign keys containing `library_id`.
   A shelf, container, positioned book, contributor, or visual item therefore
   cannot reference an object from another library even if the child UUID is
   known.
5. Contributor roles use a seeded lookup table with stable codes. The
   vocabulary can grow additively; it is not a PostgreSQL native enum.
6. Contributor names retain display spelling and order. A database-generated
   normalized name supports per-book/per-role duplicate prevention without
   replacing the credited text.
7. Edition language, original language, and translation status are distinct.
   Translation status is controlled and defaults to `UNKNOWN`; it is not
   inferred from free text.
8. Optional physical measurements use positive integer millimetres. Bookcases
   store outer dimensions, shelves store usable inner dimensions, and books
   store height, cover width, and spine thickness.
9. World geometry uses fixed-precision numeric values so it cannot contain
   floating-point NaN or infinity. Container-relative geometry remains bounded
   to its shelf's 0–100 coordinate system.
10. Reading and Loaned areas are explicit per-library visual records rather
    than overloaded integer IDs.
11. Removing a non-empty container is restricted at database level. A service
    must first perform an explicit safe relocation or clear the placement;
    deleting a container must not silently detach books.

## Migration behavior

Migration `0007_shared_catalogue_schema`:

- Adds only nullable fields or fields with safe defaults to existing books.
- Preserves existing book/library UUIDs and legacy Title/Author values.
- Seeds fifteen contributor roles.
- Creates an empty physical hierarchy and layout; it does not infer records
  for Phase 1 demonstration books.
- Is independently reversible back to Phase 3. Downgrade removes Phase 4A
  structures and returns `books` to its exact Phase 1 column set.

Before applying it to development, a verified custom-format PostgreSQL dump
was created. A disposable PostgreSQL gate proved full upgrade, constraints,
data preservation, independent downgrade, and downgrade to an empty base.
Alembic model comparison reports no pending schema operations.

## Consequences

- Server services must always scope reads and writes by membership and
  `library_id`; database constraints are defense in depth, not a substitute
  for authorization.
- Same-shelf/layer pile support, container overlap, and complete layout
  semantics still require service-level validation in Phase 4D.
- Contributor roles can be added without rewriting the contributor table, but
  a role already used by records must never be physically deleted.
- Optional dimensions do not automatically rewrite persisted visual layout.
- The catalogue API remains minimal until Phase 4B. Schema availability does
  not imply that the new metadata is yet editable from the frontend.

