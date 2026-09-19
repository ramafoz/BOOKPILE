# ADR 0010: Email-only account deletion recovery

## Decision

Deleting an account requires its current password, exact username and explicit
acknowledgement, and is rejected while it owns an active library. A successful
request immediately revokes sessions and removes Viewer memberships, then places
the account in a 48-hour quarantine.

In development, before that transaction commits BOOKPILE sends the registered
email address a cryptographically random recovery URL. In hosted environments,
the same transaction stores an encrypted outbox message and a separate worker
delivers it. Only a SHA-256 token hash is persisted outside the encrypted
payload. The URL is single-use and is the only restoration mechanism.
The ordinary login endpoint returns the same invalid-credentials response for a
pending-deletion account as for any other unavailable identity.

Immediate development delivery still rolls back the request if SMTP fails. In
hosted operation, transient failure is retried and permanent cleanup remains
blocked until the recovery message is delivered; the 48-hour window is measured
from successful delivery. After the window expires, scheduled cleanup deletes
the user and private profile object,
then removes identity and token material from the retained audit tombstone.

Account-registration invitations and shared-library invitations remain separate:
the former permit creation of an account and are issued by a platform operator;
the latter grant an existing account membership in one library and are issued by
an Owner.

## Consequences

- Knowledge of the old password is not a recovery channel.
- The API does not reveal pending-deletion identities through login.
- Losing access to the registered mailbox makes recovery impossible by design.
- Production must alert on failed or persistently pending outbox messages and
  supervise the worker independently from the API.
