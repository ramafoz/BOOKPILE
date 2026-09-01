# ADR 0010: Private authenticated book covers

## Status

Accepted, implemented, and manually validated on the Phase 4C feature branch.

## Context

Server covers must be visible to authenticated library members but must never
become anonymous public media. Uploaded files are untrusted content. The beta
also needs exact storage accounting without prematurely implementing the
shared co-Owner quota-allocation algorithm.

## Decision

- Store one optional cover record per physical book in `book_covers`.
- Store only an opaque key, controlled media type, exact encoded byte count,
  pixel dimensions, SHA-256 digest, uploader, and timestamps in PostgreSQL.
- Use a storage protocol. Development uses a private filesystem rooted under
  `.bookpile-runtime/private-objects`; production can supply a private
  S3-compatible adapter without changing catalogue records or API URLs.
- Accept at most 12 MiB and 40 million pixels in JPEG, PNG, WebP, HEIC, or
  HEIF. Reject animation and multiple pages. Apply EXIF orientation, remove
  metadata and colour profiles, flatten transparency on white, never enlarge,
  and create a maximum 900 by 1400 WebP at quality 82. Do not retain the
  original upload.
- Use random object keys and never return them to clients. Proxy reads through
  an authenticated library-scoped endpoint with `no-store` and `nosniff`.
- Permit Owner writes only; permit Owner and Viewer reads. Writes require CSRF
  and use a configurable per-user upload rate limit.
- Store a replacement before changing its database reference. If database
  persistence fails, remove the new object. Remove the former object only
  after the replacement commits. A failed post-commit cleanup can leave a
  private orphan but cannot expose or lose the active cover.
- Save a new book before uploading its optional cover. A cover failure never
  rolls back or silently deletes the valid book; the interface reports partial
  success and permits a retry.
- Defer the global 300 MB co-Owner allocation algorithm to its dedicated quota
  phase. Exact object sizes recorded here provide its future accounting input.

## Consequences

Private cover access follows the same Owner/Viewer membership boundary as the
catalogue. Files cannot be embedded through permanent public links, and browser
caches are instructed not to retain authenticated responses. Development disk
storage is replaceable rather than embedded in domain logic. The future quota
phase and production object adapter remain required before deployment.

## Verification

- A pre-migration PostgreSQL custom dump was created and listed successfully.
- Migration `0008` was rehearsed through upgrade, downgrade, and re-upgrade.
- Restoring the dump into a temporary database produced the same user,
  library, membership, book, and contributor counts as the migrated database;
  the new cover table started empty.
- Backend tests cover conversion, metadata stripping, replacement, removal,
  CSRF, Viewer read-only access, invalid input, and cross-library denial.
- The complete SQLite and opt-in PostgreSQL suites, frontend tests, TypeScript
  build, and ESLint gate pass before manual acceptance.
- Owner acceptance passed add, thumbnail/detail display, replacement,
  removal, mobile HEIC upload, and invalid-file rejection. Viewer acceptance
  passed authenticated thumbnail/detail reads, absence of write controls, and
  cross-library denial.
