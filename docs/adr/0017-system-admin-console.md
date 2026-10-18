# ADR 0017: Restricted web SYSTEM_ADMIN console before production

## Status

Accepted on 2026-10-18. This ADR supersedes only ADR 0015's decision to defer the
browser console; ADR 0015's separation between platform administration and
library membership remains binding.

## Context

The invitation beta requires routine account invitations, account-state
controls, service visibility and abuse investigation. Performing every action
through SSH is operationally fragile, while exposing raw host controls or logs
through the public application would create an unacceptable privilege bridge.

The console must therefore make a small, explicit set of platform actions safe
without granting access to private libraries or turning the web process into a
host-administration service.

## Decision

1. `SYSTEM_ADMIN` is an explicitly enrolled platform role. It is never inferred
   from username, email, library ownership or environment configuration.
2. An admin session requires a normal authenticated account and a registered
   WebAuthn/FIDO2 passkey or hardware key. SMS is not an accepted factor.
3. The admin session uses a separate Secure, HttpOnly, SameSite=Strict cookie,
   CSRF protection, 15-minute inactivity expiry and 30-minute absolute expiry.
4. Destructive actions require a WebAuthn step-up no older than five minutes.
   Enrolment/revocation, suspension/reactivation and recovery-code regeneration
   additionally require a single-use ten-minute confirmation sent to a
   separately configured operator email.
5. Offline enrolment produces one-time hashed recovery codes. Every recovery
   use is alerted and audited.
6. Admin actions are allowlisted individually. The initial catalogue is account
   invitation creation/revocation, minimum account-state listing,
   suspension/reactivation, session revocation, entitlement/aggregate capacity,
   service health and normalized security-event review.
7. The console has no shell, Docker, SQL, filesystem, secret, raw-log, token,
   email-content, impersonation or private-library browsing capability.
8. Raw logs remain host-side. The console reads normalized minimized events.
   A retained raw client IP may be revealed only inside an explicitly opened
   security incident after current WebAuthn step-up, with reason and immutable
   audit. It does not expose arbitrary raw-log search.
9. Administrative audit is append-only for application roles, hash-chained,
   integrity-checked, externally alerted and included in encrypted backups.
10. No administrator receives library data authority. Access to a private
    library still requires an ordinary explicit `OWNER` or `VIEWER` membership.

## Consequences

- The console and its complete acceptance suite are production blockers.
- The public web origin may carry the console, but possession of a normal
  session or account password alone is insufficient to enter it.
- Host recovery remains an off-host break-glass procedure protected by provider
  MFA and is not implemented by this console.
- The exact implementation and closure evidence are tracked only in
  `../BOOKPILE_MASTER_WORK_PLAN.md`.
