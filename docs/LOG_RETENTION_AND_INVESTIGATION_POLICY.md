# BOOKPILE log retention and safe-investigation policy

This document is the operational retention contract for hosted BOOKPILE. It
does not authorize broader collection. When a source contains less information
than the maximum described here, operators must not add fields merely because
the table permits them.

The legal-policy reference `PRIVACY-SECURITY-RETENTION` denotes the matching
section that must be published by the production privacy notice required in
section 10 of `BOOKPILE_MASTER_WORK_PLAN.md`. Production cannot open until the
published text and this table agree.

## Retention table

| Source | Retained fields | Purpose | Maximum duration | Deletion method | Access role | Legal-policy reference |
| --- | --- | --- | --- | --- | --- | --- |
| Caddy edge events | UTC time; remote client address; method; protocol; status; response size and duration; API/health coarse class or browser path; explicit scanner class. Request/response headers, query strings and the original API URI are deleted before writing. | Diagnose edge-only failures, abusive clients and scanner traffic before Python. | 14 days. The active file is rolled daily at 00:00 UTC or at 10 MiB, whichever occurs first; at most 14 rolls survive and rolls older than 14 days are deleted. | Caddy 2.11 time/size rolling (`roll_at`, `roll_size`, `roll_keep`, `roll_keep_for`). | Host operator with Docker authority, for a recorded incident only. Never exposed as a console log browser. | `PRIVACY-SECURITY-RETENTION`: service security and abuse prevention; legitimate interests. |
| Application request events | UTC journal time; event class; random request ID; method; FastAPI route template; status/outcome class; response byte count; keyed 16-hex client pseudonym; duration; deployment revision. | Correlate application failures and rate-limit decisions without retaining raw request content or raw client IP. | 14 days or until the 512 MiB host-journal ceiling is reached, whichever is earlier. | Docker `journald` driver plus host `MaxRetentionSec=14day`, `SystemMaxUse=512M`, daily journal files and normal journal vacuuming. | Host operator with `journalctl` authority, for a recorded incident only. | `PRIVACY-SECURITY-RETENTION`: service security and reliability; legitimate interests. |
| Security events | Event ID/type/time; optional opaque user ID; raw client IP only where the event requires attribution; allow-listed operational details such as scope, mode, revision, correlation ID, object-key HMAC and byte count. | Investigate authentication abuse, defensive-limit decisions and destructive maintenance authorization. | 180 days. | Hourly maintenance deletes rows whose `occurred_at` is at least 180 days old. | Database host operator. Future `SYSTEM_ADMIN` receives only normalized events; one raw-IP reveal requires the separately specified incident/WebAuthn/audit control. | `PRIVACY-SECURITY-RETENTION`: account/service security and abuse prevention; legitimate interests. |
| Host journal | Host and systemd unit messages plus stdout/stderr from the long-lived database, API, email worker and web containers. BOOKPILE application output follows the minimized event contracts above. PostgreSQL uses terse errors and disables statement, bind-parameter and error-detail retention. | Diagnose host, container startup, scheduler and dependency failures. | 14 days or 512 MiB, whichever is earlier; at least 1 GiB of the filesystem remains free. | systemd-journald `MaxRetentionSec`, `SystemMaxUse`, `SystemKeepFree`, `SystemMaxFileSize` and `MaxFileSec`; archived files are vacuumed by journald. | Host operator with journal authority, for a recorded incident only. | `PRIVACY-SECURITY-RETENTION`: service security and reliability; legitimate interests. |
| Sentry server errors | Redacted exception type/stack plus environment, release and the three BOOKPILE correlation/component/revision tags. No request, user, breadcrumb, message, local variables, source context, body or default PII. | Alert on and diagnose unexpected server/email-worker failures. | 90 days maximum. The operator must confirm the effective SaaS-plan retention before production and shorten this row if the provider retains for less. | Provider expiry; immediate issue deletion is available for incident response. BOOKPILE sends no attachments, traces, replays or profiles. | Sentry organization owner/administrator protected by MFA. | `PRIVACY-SECURITY-RETENTION`: error diagnosis; processor disclosure and legitimate interests. |
| Immutable admin audit (when A3 is implemented) | Operator; action; opaque target ID; reason; incident/correlation ID; UTC time; result; previous-row hash and row hash. No secrets or private catalogue content. | Accountability for privileged administration, including every raw-evidence access and mediated single-IP reveal. | 365 days. | A dedicated expiry job executed by a separate retention role may delete whole expired audit partitions; the application insert-only role cannot update or delete rows. Hash-chain checkpoints remain in encrypted operational backups for their normal 29-day lifetime. | `SYSTEM_ADMIN` can read normalized entries; the database retention role alone can expire partitions; host access remains incident-bound. | `PRIVACY-SECURITY-RETENTION`: security accountability; legitimate interests. |

## Prohibited retained content

No source above may retain cookies, authorization headers, CSRF values,
password-reset or invitation tokens, request/response bodies, email content,
raw private-object keys, book/catalogue metadata or private-library names.
Opaque database IDs, keyed client pseudonyms and keyed object-name HMACs are not
reversible substitutes for those values.

If a diagnostic change proposes any additional field, it requires a code test,
an update to this table and review of the production privacy notice before it
can be enabled.

## Raw-evidence boundary

Raw Caddy and journal evidence stays on the host. Access requires an identified
operator, an incident identifier, a written reason, a bounded time range and a
recorded result. Copy only the minimum matching lines into an incident record,
redact client addresses when they are not necessary, and never paste the full
file into chat or a ticket.

The future web console is a different boundary. It may display normalized
events and, after WebAuthn step-up, reveal the single retained IP field of one
event in one open incident. It must not provide raw-log access, arbitrary IP
search, bulk listing or export. That console rehearsal remains open until A3
and A4 exist; this policy does not claim that capability is implemented.
