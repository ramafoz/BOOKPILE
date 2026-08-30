# ADR 0004: Temporary account invitations

Status: accepted on 2026-08-30.

## Decision

The invitation-only beta uses operational **account invitations** solely to
authorize registration. They are not associated with a library or membership.
An operator creates them through a Server command; they expire after seven
days, are revocable and single-use, and persist only a hash of the random
token. Registration and consumption occur atomically.

New accounts remain `pending_verification` and cannot sign in until Phase 2E
verifies their email address.

Future **library invitations** are a different product feature. They will be
created by Owners and will grant an `OWNER` or scoped `VIEWER` membership only
after the Phase 3 membership model exists.

## Consequences

Phase 2 does not need premature library-membership tables. The temporary
account-invitation requirement can later be disabled without changing existing
users or the separate library-sharing workflow.
