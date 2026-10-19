# BOOKPILE Server defensive-security inventory

Status: D1 inventory and threat model completed on 2026-10-14. This document
records what the versioned staging/production stack does today and separates
accepted controls from the D2-D7 work that remains.

## 1. Trust boundaries and exposed services

| Boundary | Current control | Evidence | Remaining work |
| --- | --- | --- | --- |
| Internet to host | The accepted IONOS IPv4 firewall permits only TCP 22, 80 and 443; staging has no global IPv6 address or `AAAA` record | `SERVER_STAGING_PROVISIONING_CHECKLIST.md` and `SERVER_OPERATIONS_AND_SECURITY.md`; listener freshness rechecked 2026-10-14 | Recheck after firewall, DNS or network changes; do not treat inactive UFW as the control. |
| Caddy to API | API has no host `ports`; Caddy reaches `api:8100` on the internal `backend` network | Compose, `server/docker/Caddyfile`, accepted 2026-09-16 evidence and 2026-10-14 `ss`/Compose recheck | Add an automated regression assertion; no new staging acceptance is required. |
| API/worker to PostgreSQL | PostgreSQL has no host `ports` and `backend` is `internal: true` | Compose | Retain this design and test it in the production checklist. |
| API/worker to Internet | Explicit `egress` network | Compose | Document required destinations; unrestricted outbound traffic is not yet an application firewall. |
| Browser to API | Same-origin HTTPS, opaque HttpOnly session cookie, double-submit CSRF token, hosted secure-cookie validation | Auth routes, dependencies and settings | Exercise cross-origin and forged-CSRF cases in the final audit. |
| Host headers and API docs | Trusted-host middleware; wildcard hosts and hosted API docs are rejected | `main.py` and `config.py` | Verify effective staging values. |

The API, worker and web containers run as non-root with read-only root
filesystems. Deliberate writable exceptions remain: the API mounts import and
export staging volumes plus a 64 MiB `/tmp`; the worker has a 32 MiB `/tmp`;
and Caddy mounts its persistent data and configuration volumes. A compromise
can therefore modify those locations even though it cannot modify the image
root. These are useful blast-radius controls, not request-abuse controls.

## 2. Public attack surface

### Public HTTP routes

- Static application: `/`, `/index.html` and `/assets/*`.
- Health: `/health`, `/health/live`, `/health/ready`.
- Account creation: `POST /api/v1/auth/register` (invitation required).
- Email verification: resend and token confirmation.
- Password recovery: request and token confirmation.
- Login and deleted-account restoration.

All catalogue, library, member, invitation, import, export, reading, loan,
physical-layout and profile routes require a valid session. Every authenticated
state-changing route inspected also requires the CSRF dependency. Hosted API
documentation and OpenAPI endpoints are disabled by configuration validation.

### Unknown paths

- Unknown `/api/*` paths reach FastAPI, return an API 404 and are logged as the
  normalized route `unmatched` by the application request logger.
- Unknown non-API paths normally pass through `try_files {path} /index.html`
  because BOOKPILE uses client-side routes.
- A deliberately narrow, case-insensitive Caddy matcher now intercepts known
  `.env`, `.git`, WordPress-login/admin and phpMyAdmin probes before the SPA,
  returns an empty 404 and labels the access event `scanner_probe`.
- Other unknown non-API paths still receive the SPA until a broader rule can be
  proven not to break legitimate client-side routes.

The 2026-10-14 pre-change staging probe confirmed the original distinction: `/.env`,
`/.git/config` and `/wp-admin` each returned `200 text/html`, while
`/api/v1/does-not-exist` returned `404 application/json`.

## 3. Client-IP identity

BOOKPILE uses `request.client.host` for IP-based limits, session events and
account-action events. D2 closed on 2026-10-14 with an explicit application
trust boundary: Uvicorn starts with `--no-proxy-headers`, and BOOKPILE alone
accepts one syntactically valid forwarded client address from configured RFC
1918, IPv6 ULA or loopback proxy networks. Public, link-local, documentation,
CGNAT and IPv4-mapped IPv6 trust ranges are rejected in hosted configuration.

The post-deployment staging proof sent an ordinary failed login and another
with forged `X-Forwarded-For: 203.0.113.77`. Both returned the intended generic
401 and recorded the same real public client address, not the forged address
and not Caddy's `172.18.0.5` backend address. Automated tests cover trusted,
untrusted, malformed, duplicate and comma-separated forwarding values and
ensure Uvicorn cannot rewrite the peer first.

An IPv6 runtime proof remains conditional on production acquiring a public
IPv6 path; no public IPv6 address currently exists on staging.

Reference: Uvicorn's official settings document defines the default trusted
proxy as `127.0.0.1` and warns that forwarded headers must be accepted only
from trusted peers: <https://www.uvicorn.org/settings/>.

## 4. Existing request limits

Limits are shared by all API workers through atomic PostgreSQL upserts. Keys
are HMAC-SHA256 hashed with a hosted-only secret. A first blocked request
creates one `rate_limit_blocked` security event, and 429 responses include a
generic message and `Retry-After`.

| Scope | Current threshold | Key |
| --- | ---: | --- |
| Registration | 10/hour | Client IP |
| Registration | 10/hour | Invitation token |
| Login | 60/15 minutes | Client IP |
| Login | 20/15 minutes | Normalized account identifier |
| Verification/reset email actions | 10/hour | Client IP |
| Verification resend | 5/hour | Normalized email |
| Password-reset request | 5/hour | Normalized email |
| Verification/reset confirmation | 30/15 minutes | Client IP |
| Verification/reset confirmation | 10/15 minutes | Token |
| Deleted-account restoration | 60/15 minutes | Client IP (shared login policy) |
| Bibliographic lookup | 180/hour | Authenticated user |
| Cover upload | 30/hour by default | Authenticated user |
| Profile-image upload | 30/hour by default | Authenticated user |
| General API traffic | 600/minute | Validated client IP |
| Import preflight/consolidation | 6/hour user; 12/hour library | Authenticated user and authorized library |
| Portable export | 6/hour user; 12/hour library plus one active lease each | Authenticated user and authorized library |

Rate buckets older than two days are removed by maintenance. General API,
import and export controls are enforced in staging. Mutation ceilings are
implemented with independent, default-off switches pending their staging
observe/enforce acceptance. Health checks and repeated ordinary static
downloads remain outside D4; D6 covers their edge policy.

## 5. Cost and resource controls

| Operation | Existing bound | Residual risk |
| --- | --- | --- |
| Any request body through Caddy | 110 MiB maximum | Global rather than route-specific; repeated large bodies have no rate limit. |
| ZIP import | 100 MiB archive, 10,000 entries, 500 MiB expanded, 100 MiB per entry, 200:1 ratio; user/library frequency and consolidation leases | Synchronous CPU, disk and database capacity still requires monitoring. |
| Cover/profile image | 12 MiB input, 40 MP, normalized output dimensions/quality | Decode cost exists before rejection; per-user upload limit helps. |
| Portable export | Authenticated Owner authorization, user/library frequency, response-lifetime leases and temporary-file cleanup | Large permitted exports still require capacity monitoring. |
| Bibliographic lookup | Owner-only and 180/hour/user | External providers can still be pressured by multiple accounts. |
| `/health/live` | Cheap process response | Public and unlimited, appropriate for availability checks. |
| `/health/ready` | Database query plus private-object readiness call | Public and unlimited; exposes dependency names and can generate downstream work. |

The Caddy upstream response-header timeout is 15 minutes. That accommodates
large operations but also permits expensive requests to occupy resources for a
long period.

## 6. Logging, events and privacy

### Present

The API emits structured JSON per request with:

- request ID;
- method;
- normalized route template or `unmatched`;
- response status;
- aggregate outcome class;
- response `Content-Length` when known;
- a 16-hex-character HMAC client correlation key, never the raw address;
- duration;
- deployment revision.

It deliberately does not include bodies, query strings, cookies,
authorization headers or raw route identifiers. Unhandled hosted errors carry
the request ID and are sent to the configured error-reporting service.

The Caddy edge log covers all traffic so that edge-generated 413 and 502
responses remain observable. It removes the complete URI, query string,
request headers and response headers. API and health paths are replaced by the
fixed `/api/*` and `/health*` categories rather than retaining private resource
identifiers; browser paths retain their original path. Known probes carry
`event_class=scanner_probe`. Logs are private in the Caddy data volume, rotate
at 10 MiB, keep at most 14 rolled files and prune rolled files older than 14
days. Long-running container stdout/stderr logs use Docker's bounded `local`
driver with five 10 MiB files per core service.

The database also stores selected security/domain events. Security events may
contain a user ID, IP address, event type and deliberately small structured
details. Maintenance currently retains these events for 180 days.

### Missing or undecided

- Caddy 2.10.2 rotates by size but cannot rotate on a time interval. Its active
  file can therefore exceed 14 days during very low traffic even though rolled
  files have a 14-day policy. Exact temporal expiry requires a compatible
  Caddy upgrade or separately managed rotation before production.
- Sparse, purpose-specific `security_events` retain raw IP for 180 days. The
  privacy policy must distinguish those security records from the short-lived
  edge log and justify or shorten that period before production.
- No aggregate counters or alert thresholds exist for unmatched routes,
  malformed input, authentication failures or 429s.

Caddy supports structured access logs and redacts sensitive credential headers
by default, but BOOKPILE must still configure field filtering, rotation,
access, and retention explicitly. Reference: <https://caddyserver.com/docs/caddyfile/directives/log>.

## 7. Error behaviour to preserve and test

| Status | Current intent | Defensive requirement |
| --- | --- | --- |
| 401 | Missing/invalid session or invalid login credentials | Generic response; no account enumeration. |
| 403 | Valid session but failed CSRF or an explicitly forbidden operation | Do not disclose private resource data. |
| 404 | Missing or inaccessible library/resource is often collapsed to “not found” | Compare body, timing and size across absent versus unauthorized identifiers. |
| 422 | Schema/domain validation failure | Never log the submitted body; count only normalized route/status/reason class. |
| 429 | Existing scoped limit exceeded | Preserve `Retry-After`; add scope-safe telemetry without raw keys/tokens. |

## 8. Threat-to-control matrix

| Threat | Existing control | Gap | Priority |
| --- | --- | --- | --- |
| `.env`, `.git`, WordPress and panel scans | Explicit empty 404 plus minimized `scanner_probe` edge event | No aggregate threshold or temporary throttle yet | P1 monitor |
| Login brute force/account enumeration | Real client IP + identity limits, Argon2, generic invalid-credential response | No alerting/repeat-offender policy | P1 monitor |
| Registration/recovery abuse | Invitation requirement, real-IP/token/email limits, generic 202 email endpoints | Distributed abuse remains possible | P1 monitor |
| Forged forwarded IP | Private proxy allowlist, sole application parser and spoof tests | Repeat runtime proof if public IPv6 is enabled | Closed/conditional |
| Malformed request flood | Pydantic/FastAPI validation and bounded fields | No general edge limit or aggregate 422 telemetry | P1 monitor |
| Unauthorized role/ID manipulation | Server-side session, CSRF and service-layer Owner/Viewer checks | Full adversarial Owner/Viewer matrix not yet executed | P0 audit |
| Import/export exhaustion | Archive safety limits, authorization, cleanup | No per-user/library frequency or concurrency limits | P1 control |
| Health-check amplification | Separate live/ready endpoints | Ready performs dependency checks and is public/unlimited | P1 control |
| Volumetric DDoS | Caddy and small containerized surface | One VPS cannot absorb serious volumetric traffic; application limits are insufficient | P2 provider/CDN decision |

## 9. Completed foundations and next PRs

D1 closed on 2026-10-14 with the following evidence:

- the previously accepted IONOS firewall, listener and IPv6 records;
- a fresh listener and Compose-port check showing only 22, 80 and 443 on the
  host, with no published PostgreSQL or API port;
- the effective Uvicorn command, unset `FORWARDED_ALLOW_IPS`, Docker subnet and
  Caddy backend address;
- ordinary and forged-header login probes showing the shared Caddy address;
- scanner-path probes showing the SPA 200/API 404 distinction;
- current journald disk usage, with retention policy deliberately left to D3.

Response-shape/timing comparisons for 401, 403, inaccessible-resource 404,
422 and 429 remain part of the Owner/Viewer and abuse-test work. The purpose
and retention of raw IP telemetry remain a D3 privacy-policy decision, not a
reason to keep D1 open.

Subsequent progress:

1. **D2 proxy identity:** closed and accepted in staging on 2026-10-14.
2. **D3 observation baseline:** minimized Caddy and API events, bounded logs and
   explicit scanner responses implemented for staging observation. Exact
   time-based active-log expiry and aggregate thresholds remain open.
3. **D4/D6 design:** completed in
   [ADR 0016](docs/adr/0016-defensive-request-limits.md). D4 uses PostgreSQL-backed IP,
   account, user, library and costly-operation policies plus shared operation
   leases. D6 keeps Caddy's deterministic controls and reserves persistent
   host-level temporary bans for high-confidence scanner traffic. No process-
   local Caddy/Python limiter is accepted.
4. **D4 implementation:** the first infrastructure slice added explicit
   `off`/`observe`/`enforce` settings, privacy-safe observed-limit decisions,
   one shared account-identifier normalizer and PostgreSQL-backed renewable
   operation leases with monotonic fencing tokens. Subsequent slices use their
   policy-specific acceptance gates. Costly operations completed observe and
   enforce acceptance. Because staging has no representative user cohort, the
   general API ceiling uses deterministic two-worker tests, a bounded observe
   burst, an enforce burst, normal functional use and a deep check; elapsed
   24-hour observation without representative traffic is not a D4-G gate.
   The second slice connects separate user/library frequency counters to
   authorized import preflight, import consolidation and portable export
   operations. They remain inert in `off`, emit revision-labelled aggregate
   events in `observe`, return generic 429 responses only in `enforce`, and
   fail closed with 503 when PostgreSQL cannot decide. Renewable leases remain
   unwired for import consolidation until heartbeat, fenced domain commits and
   staged-object publication can be delivered together.
   The third slice connects grouped user/library leases to portable exports.
   Independent short sessions renew ownership during archive creation and the
   complete response stream; completion, disconnect and renewal failure remove
   the temporary ZIP before releasing the leases. `observe` records a
   revision-labelled collision without blocking, `enforce` returns a generic
   409, and `off` preserves the previous flow. Bounded-age cleanup for files
   abandoned by process or host failure runs in hourly maintenance and removes
   only ordinary top-level ZIP files older than the configured 24-hour TTL.
   The fourth slice connects grouped user/library leases to import
   consolidation. Cooperative ownership checks interrupt record and object
   work after heartbeat failure, while every successful consolidation fences
   both lease rows in the same PostgreSQL transaction as the imported rows,
   storage accounting and final job state. Imported covers use fresh immutable
   private keys and are not reachable until that fenced transaction commits;
   ordinary failures roll back rows and delete uploaded objects. A crashed
   process can still leave an unreferenced object, which the existing deep
   private-object audit detects; bounded automatic orphan deletion remains a
   separate recovery task because deleting an object without proving it is no
   longer part of an in-flight transaction would be unsafe.
   Costly-operation D4 was accepted in staging on 2026-10-18 at revision
   `6495d21b492dbdcaa55bf6aca0e00cf45483887e`: all six user/library scopes
   emitted the expected observation events, then the expected blocking events
   in `enforce`; ordinary import/export use and the deep operational check
   remained healthy with all 435 private objects accounted for. This closes
   the costly-operation rollout.
   The fifth slice adds an independently disabled general `/api/*` client-IP
   ceiling. It runs after trusted-proxy validation, uses the same atomic
   PostgreSQL/HMAC machinery across workers, excludes health and non-API
   traffic, records revision-labelled aggregate evidence in `observe`, returns
   a generic 429 with `Retry-After` in `enforce`, and fails closed with a
   generic 503 if no decision can be made. Observe mode was accepted at
   revision `b3700d2882fcde5c08a0ea69e585529880eaec06`, then staging moved to
   `enforce` on 2026-10-18. A fresh 650-request rehearsal returned 600 normal
   `404` responses and 50 generic `429` responses, followed by a blocked probe
   with `Retry-After: 51`; the shared HMAC bucket reached 651 and exactly one
   revision-labelled event was written without a raw IP. Health, frontend and
   static traffic left the bucket unchanged, normal authenticated use passed,
   both API workers were active, and the PostgreSQL gate starts two independent
   operating-system processes with separate configured API middleware stacks
   and database pools, synchronizes their requests to the same key and requires
   one normal response plus one generic `429`. The deep check accounted for all
   435 private objects. This closes D4-G.
   The sixth slice adds default-off authenticated-mutation and authorized-
   library-mutation policies at `240/15 minutes` and `600/15 minutes`. They use
   independent mode switches and the existing PostgreSQL/HMAC bucket schema.
   A matched-route dependency authenticates before counting, reuses that
   context in the endpoint, and uses an explicit route registry to exclude
   read-only POST operations. It consumes a library bucket only after the
   route's required member or Owner role succeeds, so missing, inaccessible or
   role-forbidden library identifiers do not spend a victim's allowance.
   Focused tests cover generic 429/503
   responses, privacy, independent user keys behind one client, a shared
   library key across co-Owners and switch isolation. The PostgreSQL gate uses
   independent processes, middleware/dependency stacks and pools for the user
   and library races. Staging revision
   `f306f30363358363d17d561268b548c2b908a8ff` passed correlated observe and
   enforce rehearsals at 241 user and 601 library attempts. A normal two-co-
   Owner workflow behind one client IP produced separate user buckets and one
   shared library bucket, all represented by 64-character HMAC keys. Both
   policies are active in `enforce`; normal use and the 435-object deep check
   remained healthy. This closes D4-M.
5. **D6 implementation:** dry-run scanner detection before enabling narrow
   10-minute bans. General volume remains alert-only for seven clean observation
   days and may then receive the ADR's high-threshold temporary ban; ambiguous
   401/404/422 signals remain alerts.
6. **D7 abuse harness:** normal navigation, bursts, scanner paths, forged IP,
   expiry, IPv4/IPv6, secret-redaction and health-check exemptions.
   The first harness slice adds `bookpile-defensive-limits status` for a
   privacy-safe aggregate of costly-operation buckets, events and leases, plus
   an explicitly confirmed synthetic rehearsal. The rehearsal is restricted
   to staging in `observe` or `enforce`, uses random identities, creates no
   accounts, libraries, archives or objects, and proves all six user/library
   policy scopes produce the expected observation or blocking event.
7. Observe D6 scanner detection for at least 24 hours before enabling its
   temporary ban. The D6 general-volume signal remains observation-only for
   seven days. D4 application limits use their policy-specific acceptance gates.

[ADR 0016](docs/adr/0016-defensive-request-limits.md) records initial staging thresholds, staged acceptance criteria,
independent disable switches and rollback. Production values remain subject to
the resulting staging measurements.
