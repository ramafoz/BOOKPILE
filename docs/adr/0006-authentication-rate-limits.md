# ADR 0006: Shared authentication rate limits

Status: accepted on 2026-08-30.

## Context

BOOKPILE Server's public identity endpoints must resist password guessing,
token probing, mail abuse, and unbounded account-enumeration attempts. An
in-memory limiter would diverge as soon as the service used more than one web
process. Redis would solve that problem but would add an unnecessary service
to the first small hosted beta.

## Decision

- Store fixed-window counters in PostgreSQL migration
  `0005_rate_limit_buckets`.
- Update each bucket with one atomic database upsert, so concurrent workers
  cannot both consume the same final permitted attempt.
- HMAC every logical key with a deployment secret. The table never stores raw
  emails, usernames, invitation tokens, action tokens, or IP keys.
- Combine an IP policy with a resource-specific policy on public identity
  operations. Return the same generic `429` response and a `Retry-After`
  header when either policy is exhausted.
- Record one structured security event when a bucket first crosses its limit,
  avoiding one audit row for every subsequent blocked request.
- Require a private rate-limit HMAC secret, HTTPS public URL, and Secure
  session cookies whenever the application is configured as production.
- Do not trust forwarding headers inside the application by default. The
  production reverse proxy must be explicitly trusted and will add a second,
  coarser rate-limit layer.

The initial policies are intentionally conservative and configurable in code:

- Registration: 10/hour per IP and invitation token.
- Login: 60/15 minutes per IP and 20/15 minutes per normalized identifier.
- Verification resend and password-reset request: 10/hour per IP and 5/hour
  per normalized email and action.
- Verification and password-reset confirmation: 30/15 minutes per IP and
  10/15 minutes per action token.

## Consequences

PostgreSQL is part of the request path for every public identity operation,
which is acceptable at the planned scale and keeps behavior consistent across
workers. The `updated_at` index supports scheduled pruning of stale buckets;
that maintenance job and reverse-proxy limits must be configured before an
external beta. A future scale test may justify replacing the implementation
with Redis without changing route policy semantics.

The generic response removes direct body/status enumeration. Synchronous email
delivery can still produce timing variation, so production delivery must move
behind an asynchronous outbox/worker before untrusted public registration.
