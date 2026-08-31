# ADR 0009: Library-scoped catalogue services

- Status: accepted
- Date: 2026-09-01
- Applies to: BOOKPILE Server Phase 4B

## Context

Migration `0007_shared_catalogue_schema` provides the shared bibliographic
tables, but schema availability is not authorization. BOOKPILE Server needs a
complete catalogue workflow that cannot leak or mutate another library's data,
preserves the approved Local-to-Server meanings, and does not yet entangle
private covers, physical layout, or personal reading data.

## Decision

1. Every repository query, count, detail lookup, metadata option, and mutation
   includes the selected `library_id`. Knowing a UUID never grants access.
2. Authentication and current membership are checked before catalogue access.
   Owners may read and write. Viewers may read all shared bibliographic fields
   but cannot create, replace, or delete records.
3. POST, PUT, and DELETE require CSRF protection. Successful mutations record
   structured library audit events with the acting user and book identifier.
4. PUT is a complete replacement of editable shared metadata and ordered
   contributors. Contributor replacement and the book update commit in one
   transaction, so an invalid role or contributor cannot leave partial data.
5. Delete requires the client to repeat the exact current title. This guards
   accidental interaction but does not replace authorization.
6. ISBNs use checksum validation. Controlled metadata uses the Phase 4A
   vocabulary. Genres are normalized, deduplicated case-insensitively, and
   stored alphabetically. Translation and multiple-author invariants are
   validated before persistence.
7. Search is simple across title, legacy author, series, and structured
   contributor names. Advanced filtering uses OR within repeated values of one
   field and AND across different fields. Sorting is restricted to an explicit
   safe column map and result pages have bounded limits.
8. Existing pre-Phase-4B books remain readable. A legacy `Multiple authors`
   record must acquire at least two structured AUTHOR contributors when an
   Owner next replaces it.

## Boundaries

- Covers and authenticated image delivery belong to Phase 4C.
- Bookcases, shelves, containers, positions, and visual layouts belong to
  Phase 4D even though their tables already exist.
- Reading sessions, reading status, statistics, custody, and loans remain
  personal/shared Phase 5 concerns.
- Goodreads review URLs are personal Owner/book metadata, not shared
  bibliography. Phase 4B therefore neither accepts nor serializes the dormant
  Phase 4A shared-book column; Phase 5 will add the correct per-Owner relation.
- Local ZIP conversion remains Phase 4E. Phase 4B never opens a Local database.

## Verification

- Fast backend tests cover Owner CRUD, Viewer denial, isolation, filters,
  options, normalization, validation, audit events, and atomic rollback.
- Frontend tests cover advanced query serialization, CSRF writes, and
  validation-error presentation; TypeScript build and ESLint pass.
- The disposable PostgreSQL integration gate applies all migrations, performs
  a real Phase 4B write with ordered contributors, and rolls every migration
  back while preserving the expected earlier catalogue rows.
- The populated Local v1 worktree remains clean on `release/local-v1` and the
  Server development database retains its pre-Phase-4B record counts.
