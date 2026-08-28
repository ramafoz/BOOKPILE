# ADR 0003: Identity and session policy

Status: accepted on 2026-08-28.

## Context

BOOKPILE Server needs first-party accounts without weakening the independent
BOOKPILE Local v1 application. Identity is being added incrementally before
membership and invitation workflows, so each migration can be verified and
reversed independently.

## Decision

- Passwords will accept 12–128 Unicode characters, including spaces, without
  composition rules. Phase 2B will hash them with Argon2id.
- Usernames contain 3–30 ASCII letters, digits, or underscores. They are
  normalized to lowercase and compared case-insensitively. Reserved names are
  enforced by the future account service.
- Email addresses are normalized to lowercase and must be verified before an
  account can accept invitations or enter a library.
- Session credentials will be opaque random values. The database stores only
  their hashes and separate CSRF-token hashes.
- Normal sessions expire after 7 days of inactivity and have a 30-day absolute
  lifetime. Explicit `remember me` sessions have a 90-day absolute lifetime.
- Invitation links expire after 7 days, verification links after 24 hours, and
  password-reset links after 30 minutes. Verification links can be regenerated.
- Development email will use Mailpit. A production provider is deliberately
  deferred.
- Security-relevant actions use structured audit events that may outlive a
  deleted user without retaining an account foreign-key association.

## Consequences

Migration `0002_identity_foundation` adds users, opaque-session records, and
security events. It does not expose authentication endpoints, accept passwords,
send mail, or alter Local v1. Authentication behavior will be implemented and
tested in later Phase 2 increments.
