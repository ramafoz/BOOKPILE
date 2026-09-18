# Durable email outbox

Hosted BOOKPILE records email intent in PostgreSQL in the same transaction as
the account action. A separate `bookpile-email-worker` process claims one row
with a lease, decrypts it only in memory, sends it through authenticated
encrypted SMTP and marks it sent. Both STARTTLS and implicit TLS are supported;
development remains synchronous so Mailpit is
simple to use.

The payload (recipient, subject and URL-bearing body) is AES-GCM encrypted with
`BOOKPILE_SERVER_EMAIL_OUTBOX_ENCRYPTION_SECRET`; that secret must not live in
the database or repository. Database readers can see purpose and queue state,
but not addresses or recovery links. Message IDs are deterministic so a worker
crash around SMTP acknowledgement is detectable by the provider. Delivery is
at-least-once: a rare crash after SMTP accepts a message can still duplicate it.

Every account message is generated from the shared BOOKPILE transactional-email
presentation. It contains equivalent complete plain-text and responsive HTML
parts, an email-client-safe bookshelf motif built without remote resources,
visible fallback URLs and no tracking pixels. Verification, password reset and
account recovery therefore share one accessible visual language while retaining
purpose-specific subjects, expiry and security guidance. The SMTP envelope adds
an RFC `Date`, deterministic `Message-ID`, `Auto-Submitted: auto-generated` and
auto-response suppression headers.

Migration `0022_email_delivery_receipts` stores only the successful SMTP response
code and a strictly parsed provider queue identifier when the server supplies
one. Both values are also included in the privacy-safe `email_sent` log. They
allow provider tracing without decrypting the recipient, body or action URL.
`SENT` continues to mean that the authenticated SMTP server accepted the
message; it does not prove inbox placement. Downstream delivery, spam placement
and bounces remain provider/mailbox evidence.

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

Providers with a low delivery quota can impose a delay after every processed
row without slowing empty-queue polling:

```bash
bookpile-email-worker --poll-seconds 2 --processed-delay-seconds 11
```

Operational alerts must cover a stopped worker, old `PENDING` rows, reclaimed
leases and any `FAILED` row. Logs and dashboards may use message UUID, purpose,
state, attempt count, SMTP response code and validated provider queue ID; they
must never expose recipient, raw SMTP text or decrypted content.
Do not downgrade migration 0021 while the queue contains rows.
