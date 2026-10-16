# ADR 0016: Shared defensive request limits and hostile-edge response

## Status

Accepted on 2026-10-16. This ADR fixes the D4 and D6 design; acceptance and the
first infrastructure implementation do not enable new limits or host bans.

## Context

BOOKPILE already has shared fixed-window limits for authentication, email
actions, bibliographic lookup and image uploads. Their counters are atomic
PostgreSQL rows and their logical keys are HMAC protected. Caddy also rejects
bodies above 110 MiB and returns an empty 404 for a narrow set of known scanner
paths.

The remaining risks are different in nature:

- anonymous request volume and malformed traffic are keyed by client address;
- authenticated activity can be keyed by a stable user rather than an address;
- co-Owners can collectively pressure one library;
- imports, exports and image processing cost much more than ordinary reads;
- two API workers must make the same decision;
- one VPS cannot absorb a volumetric denial-of-service attack.

A limiter held only in a Python or Caddy process would split counters between
workers and lose them on restart. Stock Caddy 2.10.2 has
[request matchers](https://caddyserver.com/docs/caddyfile/matchers), static
responses, body limits and [access logs](https://caddyserver.com/docs/caddyfile/directives/log),
but no built-in distributed rate-limit directive. BOOKPILE will not hide that
gap behind a process-local third-party plugin.

## Vocabulary and programme boundaries

- **D4** is the shared application limit layer. It knows validated client
  addresses, normalized account identifiers, authenticated users, authorized
  libraries and operation cost.
- **D5** is aggregate monitoring and alerting. It consumes the normalized
  events from D3/D4 but does not block requests.
- **D6** is temporary hostile-edge response. It acts only on high-confidence
  edge evidence and is not a substitute for provider DDoS protection.
- **D7** is the abuse and regression harness used before and after enforcement.

## Existing controls retained unchanged

| Operation | Scope | Current limit | Store |
| --- | --- | ---: | --- |
| Registration | client IP | 10/hour | PostgreSQL |
| Registration | invitation token | 10/hour | PostgreSQL |
| Login | client IP | 60/15 minutes | PostgreSQL |
| Login | normalized username/email | 20/15 minutes | PostgreSQL |
| Verification/reset email action | client IP | 10/hour | PostgreSQL |
| Verification resend | normalized email | 5/hour | PostgreSQL |
| Password-reset request | normalized email | 5/hour | PostgreSQL |
| Verification/reset confirmation | client IP | 30/15 minutes | PostgreSQL |
| Verification/reset confirmation | action token | 10/15 minutes | PostgreSQL |
| Deleted-account restoration | client IP | 60/15 minutes | PostgreSQL |
| Bibliographic lookup | authenticated user | 180/hour | PostgreSQL |
| Cover upload | authenticated user | 30/hour | PostgreSQL |
| Profile-image upload | authenticated user | 30/hour | PostgreSQL |
| Any body reaching Caddy | request | 110 MiB | Caddy hard bound |
| ZIP import | archive | 100 MiB compressed, 10,000 entries, 500 MiB expanded, 100 MiB/entry, 200:1 ratio | Application validation |
| Cover/profile image | upload | 12 MiB and 40 MP | Application validation |

The existing authentication limits remain enforced even if the new defensive
programme is put into observation or disabled.

## Decision

### 1. Keys and ownership

Every application key is HMAC-SHA256 protected with the existing hosted-only
rate-limit secret. Raw IP addresses, account names, emails, tokens, user IDs
and library IDs are never stored in `rate_limit_buckets`.

| Scope | Canonical logical key | When it is available |
| --- | --- | --- |
| Client IP | validated effective address, canonicalized by `ipaddress` | before authentication |
| Normalized account | trimmed and lower-cased username/email using one helper shared with authentication | after schema validation |
| Authenticated user | immutable user UUID | after session validation |
| Library | immutable library UUID | only after membership/authorization succeeds |
| Costly operation | operation name combined with user and, where applicable, authorized library | immediately before work starts |

An inaccessible or nonexistent library must not consume that library's bucket;
otherwise the limiter would become an existence oracle and let outsiders
exhaust a victim's allowance. IP limits may still count such a request.

### 2. Shared storage

Fixed-window frequency limits continue to use atomic PostgreSQL upserts in
`rate_limit_buckets`. This is already safe across both API workers and avoids a
new Redis service during the private beta.

Concurrency limits require a separate additive `operation_leases` table with:

- `scope` and HMAC `key_hash` as the uniqueness boundary;
- an opaque lease ID;
- a monotonically increasing fencing token;
- `acquired_at`, `renewed_at` and `expires_at`;
- atomic acquire-if-absent-or-expired semantics;
- compare-and-swap renewal and release using both lease ID and fencing token;
- expiry recovery after worker failure.

A frequency bucket is not a concurrency lock. Database connection-pool limits
are capacity controls and must not be presented as user-facing request limits.
When one operation needs both a user and library lease, both acquisitions occur
in one database transaction. Failure to acquire either leaves neither lease
held. Authorized attempts consume frequency before work starts, whether or not
later domain validation succeeds; requests denied before library authorization
never consume the library key.

Leases use a short renewable lifetime rather than a maximum operation duration:
the initial staging values are a two-minute TTL and a heartbeat no slower than
30 seconds. Heartbeats use a separate short database session so a long-running
operation or transaction cannot hide renewal. A check immediately before a
write is not sufficient fencing. Every protected database commit must lock or
compare-and-swap the lease row using the lease ID, fencing token and database
clock **inside the same transaction** as the domain writes. The transaction
renews the unexpired lease and holds that row lock through commit; a new owner
cannot acquire the expired row between validation and commit. A protected
operation that uses multiple commits repeats this atomic fence for each one.

Object storage has no transaction shared with PostgreSQL. Object-producing
work therefore writes immutable, private, lease-scoped staging keys first.
Those objects are not reachable by an API record. Only a database transaction
that passes the atomic fence may publish them by creating the authoritative
database reference. A stale worker may leave an unreferenced staging object,
but cannot replace or expose the current owner's object; bounded-age
maintenance removes such orphans. Destructive provider actions occur only
after a fenced database state transition, must be idempotent and may target
only the exact immutable key recorded by that transition, never a reusable
logical key. If renewal or ownership fails, the worker aborts without
publishing new durable state. Only the current fenced owner can release the
lease.

### 3. Initial staging matrix

These values are deliberately roomy for normal beta use and deliberately low
for expensive operations. They start in observation mode; enforcement follows
only after D7 and at least 24 hours of representative staging traffic.

| Class | Scope | Initial value | Mode after observation | Response |
| --- | --- | ---: | --- | --- |
| All API requests | client IP | 600/minute | enforce | Generic 429, `Retry-After` |
| Authenticated mutations | user | 240/15 minutes | enforce | Generic 429, `Retry-After` |
| Authorized library mutations | library | 600/15 minutes | enforce | Generic 429, `Retry-After` |
| Bibliographic lookup | client IP | 300/hour | enforce alongside existing 180/hour/user | Existing generic lookup 429 |
| Bibliographic lookup | library | 360/hour | enforce | Existing generic lookup 429 |
| Cover upload | library | 120/hour | enforce alongside existing 30/hour/user | Existing generic upload 429 |
| Import preflight/upload | user | 6/hour | enforce | Generic costly-operation 429 |
| Import preflight/upload | library | 12/hour | enforce | Generic costly-operation 429 |
| Import consolidation | user | 6/hour plus lease | enforce | Generic costly-operation 429; 409 for concurrent work |
| Import consolidation | library | 12/hour plus lease | enforce | Generic costly-operation 429; 409 for concurrent work |
| Import/consolidation | user and library | one renewable fenced lease each; 2-minute TTL, heartbeat at most every 30 seconds | enforce | 409 while already active; 429 for frequency |
| Portable export | user | 6/hour and one renewable fenced response-lifetime lease | enforce | Generic costly-operation 429 |
| Portable export | library | 12/hour and one renewable fenced response-lifetime lease | enforce | Generic costly-operation 429 |
| Rearrangement preview/apply | user | 120/minute | observe first; enforce only if normal UI remains below 25% | Generic 429 |
| Rearrangement preview/apply | library | 240/minute | observe first; enforce only if normal UI remains below 25% | Generic 429 |
| Public `/health/live` | client IP at edge | 120/minute | D6 observe first; never add a database dependency | Temporary edge response only after acceptance |
| Public `/health/ready` | client IP at edge | 30/minute | D6 observe first; internal Docker probe bypasses Caddy | Temporary edge response only after acceptance |

Ordinary authenticated reads do not receive an additional user/library limit
in the first implementation. The client-IP ceiling covers gross abuse while
avoiding breakage when a catalogue legitimately loads hundreds of private
covers. D3 measurements may justify a later read policy.

The 600/minute IP ceiling is not advertised as DDoS protection. It only bounds
moderate abusive traffic reaching the application. Shared NATs are protected
by the separate user/library limits and by keeping edge bans narrow.

### 4. Enforcement placement

| Control | Enforcement point | Reason |
| --- | --- | --- |
| Body size, known scanner paths, static routing, upstream timeouts | Caddy | Deterministic and cheapest before Python |
| General API IP frequency | application middleware backed by PostgreSQL | Uses the validated client address and remains consistent across workers |
| Account, user and library frequency | route/dependency layer backed by PostgreSQL | Requires normalization, session and authorization context |
| Costly-operation frequency and leases | service plus response-lifecycle boundary backed by PostgreSQL | Must cover work and, for exports, the complete stream and cleanup |
| High-confidence scanner temporary ban | host firewall driven by minimized Caddy events | Stops repeat probes before TLS/application work without a Caddy plugin |
| Volumetric DDoS | hosting provider or future CDN/WAF | A single VPS and its database cannot absorb it safely |

The general IP middleware excludes static assets and counts `/api/*` only.
Health limits are derived from persisted edge events; `/health/live` must stay
independent of PostgreSQL so it can report a live API process during a database
failure. Internal container health traffic reaches the API directly and is not
treated as public traffic. No client-supplied forwarding header participates
until the trusted-proxy middleware has validated and rewritten the ASGI scope.

Before either public health threshold can leave observation mode, Caddy must
replace the current aggregate `/health*` label with three fixed privacy-safe
classes: `health_class=live` for the exact `/health/live` path,
`health_class=ready` for the exact `/health/ready` path and
`health_class=other` for every remaining `/health*` request. Queries and the
original URI remain deleted. D6 must refuse to load separate health jails if
these labels are absent or if a fixture can match one request in both classes.

### 5. D6 temporary edge response

D6 uses Fail2ban (or an equivalently reviewed host service) against Caddy's
private JSON access log and an nftables set dedicated to BOOKPILE. The future
Compose change must expose only that log through a dedicated host directory
such as `/var/log/bookpile`, writable by the Caddy container and readable only
by root/the host service; it must not depend on Docker's internal volume path.
Fail2ban's `dbfile` must be the persistent
`/var/lib/fail2ban/fail2ban.sqlite3`, never `:memory:` or `None`, so active bans
and log positions survive a daemon restart. The minimized source events also
remain on disk under the D3 retention policy; a restart may delay a threshold
decision but cannot erase its evidence. It must never read request bodies,
queries, cookies or authorization headers.

Initial staging policy:

| Signal | Find window | Threshold | Ban | Initial mode |
| --- | ---: | ---: | ---: | --- |
| `event_class=scanner_probe` | 60 seconds | 60 | 10 minutes | observe/dry-run for 24 hours, then enforce |
| Repeated scanner bans | 24 hours | 3 completed bans | 1 hour | observe until one week of evidence |
| General request volume | 60 seconds | 1,200 | candidate 10-minute ban after seven clean observation days; D5 alert first | observe |
| `health_class=live` | 60 seconds | 120 | candidate 10-minute ban after distinct-label and monitor validation | observe |
| `health_class=ready` | 60 seconds | 30 | candidate 10-minute ban after distinct-label and monitor validation | observe |
| Authentication 401/429 | any | no edge ban | application limits only | observe |
| API 404/422 | any | no edge ban until Owner/Viewer and malformed-input baselines exist | D5 alert only | observe |

SSH is outside these rules and retains its own provider/host policy. Operator
addresses are not permanently allowlisted; emergency unban remains available
through the IONOS console. IPv4 and IPv6 require equivalent rules before a
public IPv6 address is enabled.

### 6. Configuration, privacy and observability

New controls have a separate hosted setting with `off`, `observe` and
`enforce` modes. `off` affects only D4 additions, never the accepted
authentication limits. Its initial default is `off`, so deployment alone cannot
silently enable a new policy. Thresholds are explicit validated settings, with
safe upper bounds; zero is not overloaded to mean unlimited.

Observation mode consumes shared counters and emits aggregate policy/scope
events but does not return 429. Events contain the policy name, scope class,
outcome and deployment revision, never the logical key. A blocked request
emits one event when a fixed window first crosses its threshold, matching the
existing behavior.

Dashboards and alerts aggregate 429s, lease conflicts, scanner observations,
temporary bans and 5xx responses. Raw edge addresses remain subject to the D3
retention/privacy decision. HMAC client correlation is not reversible and is
not a firewall key.

If PostgreSQL cannot make an atomic D4 decision, the protected API operation
returns 503 rather than silently bypassing enforcement. This does not apply to
`/health/live`, which deliberately has no database dependency. A D6/Fail2ban
failure is fail-open for HTTP availability, raises an operational alert and
must never alter Caddy's ability to serve or proxy requests.

An export lease covers archive creation **and the complete response body**. It
is renewed while `FileResponse` is streaming and is released only by the same
response-completion/disconnect cleanup that removes the temporary ZIP. A slow
download therefore cannot overlap another export for the same key. If the
worker dies, lease expiry permits recovery. D4 implementation must also add a
bounded-age maintenance cleanup for abandoned export files; no such cleanup is
assumed to exist today. Implementation tests must exercise normal completion,
slow streaming, client disconnect, renewal failure, worker failure and stale-
file cleanup.

### 7. Rollout and acceptance

1. Add and test the distinct `live`, `ready` and `other` Caddy health labels;
   keep every health response in observation mode.
2. Add configuration, shared D4 policies and leases with mode `off`.
3. Deploy staging in `observe`; run D7 normal-navigation and abuse scenarios.
4. Collect at least 24 hours including normal mobile/catalogue/map/import and
   export use. Raise a threshold if legitimate peaks exceed 25% of it.
5. Enforce costly-operation limits and leases first.
6. Enforce general IP, user and library limits.
7. Install D6 in dry-run, validate parsed addresses and counts, then enable the
   scanner-only 10-minute ban.
8. Enable the 1,200/minute general-volume ban only after seven observation
   days with no legitimate threshold crossing. Keep 401/404/422 signals
   alert-only until evidence supports safe blocking.

Acceptance requires tests for two concurrent workers, fixed-window reset,
lease acquisition/renewal/fencing/release, a stale worker paused after its
initial check while a new owner acquires the lease, atomic rejection of the
stale database commit, private staged-object publication and orphan cleanup,
slow export streaming and disconnect cleanup, multiple users behind one IP,
multiple co-Owners in one library, unauthorized library identifiers,
`Retry-After`, distinct non-overlapping health labels, IPv4/IPv6
canonicalization, forged forwarding headers, restart persistence, dry-run and
emergency unban. Normal frontend and external health monitoring must complete
without a 429.

## Disable and rollback

Application rollback is configuration-first:

1. set the new defensive mode from `enforce` to `observe` (preferred) or
   `off`;
2. redeploy the same application revision;
3. confirm live/ready and normal authentication;
4. retain additive tables and counters for diagnosis; do not downgrade a
   database migration during an application rollback.

D6 rollback is independent:

1. disable only the BOOKPILE jail;
2. reload Fail2ban;
3. remove only the dedicated BOOKPILE nftables set/rules;
4. verify ports 22, 80 and 443 and record the reason/time/operator.

The deployment script must not automatically enable D6. Host installation and
rollback require a separate, rehearsed operator procedure. The pre-deployment
backup remains mandatory for schema changes, but restoring it is not part of
ordinary limit rollback.

## Consequences

PostgreSQL receives an extra write for each counted API request. That is
acceptable for the private-beta scale but must be load-tested; if it becomes
the bottleneck, Redis may replace the repository without changing policy
semantics. Edge controls reduce obvious scanner work but do not make one VPS a
DDoS appliance. Conservative staged enforcement and independent kill switches
reduce the chance of locking out legitimate users.
