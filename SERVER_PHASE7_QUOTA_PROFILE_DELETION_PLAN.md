# BOOKPILE Server Phase 7 — profiles, quota allocation and safe deletion



Status: active on `feature/server-storage-quota`; 7A–7D are complete. Phase 6 is merged into
`main`. This phase changes Server only and leaves released Local v1 untouched.

## 1. Product contract

- Free beta accounts receive 100,000,000 bytes of logical persistent storage.
- Quota is an entitlement, not a hard-coded constant: later plans or per-account
  overrides may raise it without changing catalogue data.
- Private objects use their exact stored byte size. Relational records use a
  deterministic, versioned logical-size formula, never PostgreSQL physical size.
- Every shared-library byte is allocated exactly once across its Owners; Viewers
  provide no capacity and receive no allocation.
- An account sees only its own total usage and per-library allocation. No
  response reveals another Owner's capacity, usage or limiting identity.
- Temporary upload/import processing storage is operational capacity and does not
  consume account quota. Phase 8 ZIP preflights the final processed logical size
  before an atomic import; ZIP size alone never determines acceptance.

## 2. Storage presentation

The protected user control opens a private account page. Storage contains no
numeric byte or percentage labels:

- one stable-colour bar per owned library, whose denominator is the account's
  current used space;
- one stacked total bar, whose denominator is the account entitlement and whose
  coloured segments reuse the library colours;
- any account-owned profile object is a separate neutral-colour `Account data` segment;
- when one library is the sole contributor and there is no account-data segment,
  omit its redundant contribution row and show only the total account bar;
- accessible progress semantics remain available to the signed-in account without
  exposing another user's values.

For 5 MB in Salón and 25 MB in Oficina, their contribution bars are 5/30 and
25/30; the total is a blue 5/100 segment plus red 25/100 and 70/100 empty.

## 3. Private account profile

Initial editable optional fields are profile-only name, timezone, gender, city, state,
country, date of birth and profile image. Email, account/security state, quota,
allocations and sessions are always private.

Privacy is deliberately grouped into four controls: profile image, profile-only
name, timezone, and personal data (gender, location and date of birth). Each has
one visibility:

- `PRIVATE`;
- `SHARED_LIBRARY_MEMBERS`;
- `AUTHENTICATED`.

No anonymous profile is available during beta. Profile images use authenticated
delivery, decode validation, pixel/upload limits, metadata stripping and controlled
WebP re-encoding; the original is discarded and the resulting bytes count as
`Account data`.

Gender is `UNSPECIFIED`, `MALE`, `FEMALE` or `CUSTOM`. Male, Female and blank show
no separate pronoun field. Custom exposes `custom_gender` plus a
preferred-pronoun selector (`MALE`, `FEMALE`, `NEUTRAL`); Neutral may carry one
free-text pronoun value. Only Custom profiles expose pronouns, which are visible
to authenticated users regardless of personal-data visibility.

## 4. Allocation rules

For library L and Owner U, non-negative integer-byte allocations satisfy:

```text
sum(allocation[L,U]) = logical_size[L]
sum(account_data[U] + allocation[L,U] for all owned L) <= entitlement[U]
```

The deterministic solver first seeks feasibility, then minimizes changes to prior
allocations, then imbalance. All affected accounts, memberships, library usage and
allocations are locked in one transaction. Failure reports insufficient shared
capacity without identifying the constrained co-owner.

## 5. Deletion and recovery

Shared-library deletion requires reauthentication, exact library name and explicit
acknowledgement of affected books, covers, readings, loans and members. One atomic
transition snapshots memberships/scopes and allocations, revokes access, releases
quota and quarantines objects for 48 hours. Any former Owner may request complete
recovery after reauthentication, provided a full allocation is feasible. There is
no partial recovery. Final deletion removes active data/objects; inaccessible
operational backups may retain tombstones for at most 30 days.

## 6. Increments

### 7A — accounting contract and pure allocator

Status: complete. Logical accounting v1, exact object-byte charging and the
global deterministic allocator pass worked-example, balance, retention,
validation and insufficient-capacity tests plus the full Server regression.

Implement versioned logical-size rules, entitlement and allocation value objects,
the deterministic solver, worked examples and property/edge tests. No schema or UX.

### 7B — additive schema and scoped services

Status: complete. Backup restoration was rehearsed before migration `0015`; the
active database then migrated without data loss. Profile visibility and gender
shape are database-guarded, existing users received entitlement rows, logical
usage was backfilled only for libraries with an actual Owner, allocation totals
reconcile exactly, and private field projections plus authenticated pronouns are
covered by regression tests. Historical unowned Demo seeds remain deliberately
unallocated rather than being silently assigned to an account.

After backup/restore rehearsal, add account profile/visibility, entitlement,
library usage, allocation and deletion-tombstone tables. Add tenant-safe constraints,
locking repositories, private projections and migration guards.

### 7C — enforcement and membership integration

Status: complete. Catalogue, cover, physical-layout, reading, loan and membership
writes now flush, lock, recalculate and allocate before one shared commit. Capacity
failure has a non-identifying API response and rolls back domain rows, audit rows
and newly stored cover objects. Owner removal is rejected atomically when remaining
Owners cannot absorb the allocation. A disposable PostgreSQL gate proves two
individually valid but jointly excessive concurrent writes serialize and exactly
one succeeds.

Charge cover/profile-object writes and relevant relational growth, recalculate
allocations atomically, and integrate Owner add/remove and quota races. Ordinary
reads/deletions remain available at the limit.

### 7D — profile, security shell and storage UX

Status: complete. The protected username opens a responsive private account
workspace with grouped privacy, safe profile-image handling, private account
identity, password change and session controls. Authenticated members can open
privacy-projected profiles from shared-library usernames. Username remains the
product identity; optional Name appears only in the profile. Library settings now
hang from the Owner's library selector and distinguish structural creation/removal
from visual map editing. Non-numeric storage bars suppress redundant single-source
breakdowns. Desktop/mobile acceptance and backend/frontend regression gates pass.

Add the private profile page, field visibility, safe profile image, security menu
entry and non-numeric coloured contribution/stacked bars. Validate responsive and
accessibility behaviour without leaking other Owners' usage.

### 7E — shared deletion, quarantine and recovery

Implement reauthenticated deletion, access revocation, quota release, 48-hour
quarantine, any-former-Owner recovery with allocation preflight and final cleanup.

### 7F — final compatibility and release gates

Run full SQLite-independent Server, PostgreSQL, concurrency, privacy, migration,
frontend and operational gates; document and request approval before merging.

## 7. Explicit deferrals

- Local ZIP import/export implementation remains Phase 8. A compressed ZIP may be
  smaller than its extracted/final data, so Phase 8 will enforce archive-bomb limits
  and quota against the final staged logical charge.
- Paid billing and checkout are not Phase 7; only entitlement-ready limits are.
- Public anonymous profiles, social features and automated deletion emails remain
  later phases.
