# Durable email outbox

Hosted BOOKPILE records email intent in PostgreSQL in the same transaction as
the account action. A separate `bookpile-email-worker` process claims one row
with a lease, decrypts it only in memory, sends it through authenticated
STARTTLS SMTP and marks it sent. Development remains synchronous so Mailpit is
simple to use.

The payload (recipient, subject and URL-bearing body) is AES-GCM encrypted with
`BOOKPILE_SERVER_EMAIL_OUTBOX_ENCRYPTION_SECRET`; that secret must not live in
the database or repository. Database readers can see purpose and queue state,
but not addresses or recovery links. Message IDs are deterministic so a worker
crash around SMTP acknowledgement is detectable by the provider. Delivery is
at-least-once: a rare crash after SMTP accepts a message can still duplicate it.

Retries use bounded exponential delay and leased claims allow another worker to
recover abandoned work. Revoked/consumed account actions and recovered account
deletions are cancelled before delivery. Account-action expiry and the 48-hour
account-deletion recovery window are extended from successful delivery, not
merely from enqueue time. Permanent account cleanup will not pass an undelivered
recovery message.

Run one item for diagnostics:

```powershell
bookpile-email-worker --once
```

Run continuously (the production Compose file already defines this service):

```powershell
bookpile-email-worker --poll-seconds 2
```

Operational alerts must cover a stopped worker, old `PENDING` rows, reclaimed
leases and any `FAILED` row. Logs and dashboards may use message UUID, purpose,
state and attempt count; they must never expose recipient or decrypted content.
Do not downgrade migration 0021 while the queue contains rows.
