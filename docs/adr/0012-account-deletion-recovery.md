# ADR 0010: Email-only account deletion recovery

## Decision

Deleting an account requires its current password, exact username and explicit
acknowledgement, and is rejected while it owns an active library. A successful
request immediately revokes sessions and removes Viewer memberships, then places
the account in a 48-hour quarantine.

Before that transaction commits, BOOKPILE sends the registered email address a
cryptographically random recovery URL. Only a SHA-256 hash is persisted. The URL
is single-use, expires with the quarantine and is the only restoration mechanism.
The ordinary login endpoint returns the same invalid-credentials response for a
pending-deletion account as for any other unavailable identity.

If email delivery fails, the entire deletion transaction rolls back. After the
window expires, scheduled cleanup deletes the user and private profile object,
then removes identity and token material from the retained audit tombstone.

Account-registration invitations and shared-library invitations remain separate:
the former permit creation of an account and are issued by a platform operator;
the latter grant an existing account membership in one library and are issued by
an Owner.

## Consequences

- Knowledge of the old password is not a recovery channel.
- The API does not reveal pending-deletion identities through login.
- Losing access to the registered mailbox makes recovery impossible by design.
- Production must provide reliable transactional email monitoring; asynchronous
  delivery would require an outbox before replacing the current fail-closed send.
