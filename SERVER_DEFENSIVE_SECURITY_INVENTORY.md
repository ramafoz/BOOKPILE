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
- Unknown non-API paths pass through `try_files {path} /index.html`; scanner
  probes such as `/.env`, `/.git/config` and `/wp-admin` are therefore expected
  to receive the SPA entry point with status 200 rather than a 404.
- Caddy access logging is not enabled in the versioned Caddyfile. Those
  non-API probes are consequently invisible to BOOKPILE's API request log.

This means a rule based on “60 different 404s” cannot currently detect the
common scanner traffic described in the threat model.

The 2026-10-14 staging probe confirmed the distinction: `/.env`,
`/.git/config` and `/wp-admin` each returned `200 text/html`, while
`/api/v1/does-not-exist` returned `404 application/json`.

## 3. Client-IP identity

BOOKPILE currently uses `request.client.host` for IP-based limits, session
events and account-action events. The versioned Uvicorn command does not set
`--forwarded-allow-ips`; Uvicorn 0.34.3 trusts forwarded headers only from
`127.0.0.1` by default, while Caddy connects over a Docker network. The
versioned Compose environment does not establish an explicit trust rule. The
2026-10-14 runtime inspection confirmed that `FORWARDED_ALLOW_IPS` is unset,
the Uvicorn command supplies no equivalent argument, and Caddy currently has
the backend address `172.18.0.5`.

The defect is now confirmed: the two existing `login_failed` security events
inspected on 2026-10-14 both recorded `172.18.0.5`, which is Caddy's current
backend address, rather than the originating Internet client. Consequently,
all clients currently share one effective key for limits described as IP-based.
Blindly trusting `*` would restore forwarded attribution but would make
spoofing possible if the API were ever reached through another path.

A controlled pair of public login failures completed the baseline proof. The
ordinary request and a request carrying the forged value
`X-Forwarded-For: 203.0.113.77` both returned the intended generic 401 and both
produced `login_failed` events with `ip_address = 172.18.0.5`. Caddy therefore
prevents the external spoof from reaching the application as client identity,
but Uvicorn also discards Caddy's legitimate forwarded client address.

Required D2 correction and acceptance proof before adding IP blocking:

1. Configure an explicit Caddy-to-Uvicorn trust boundary.
2. Send two requests from distinct known client addresses and show distinct
   `request.client.host` values without publishing those addresses.
3. Send a forged `X-Forwarded-For` from outside Caddy and prove it is ignored or
   overwritten.
4. Send a controlled forwarded value through Caddy and prove it is accepted.
5. Repeat for IPv6 when an IPv6 public path exists.
6. Add automated proxy-boundary and spoofing tests.

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

Rate buckets older than two days are removed by maintenance. No current limit
covers general reads/writes, malformed requests, unknown routes, health checks,
imports, exports, repeated downloads or request concurrency.

## 5. Cost and resource controls

| Operation | Existing bound | Residual risk |
| --- | --- | --- |
| Any request body through Caddy | 110 MiB maximum | Global rather than route-specific; repeated large bodies have no rate limit. |
| ZIP import | 100 MiB archive, 10,000 entries, 500 MiB expanded, 100 MiB per entry, 200:1 compression ratio | CPU, disk and database work is synchronous and not rate-limited per user/library. |
| Cover/profile image | 12 MiB input, 40 MP, normalized output dimensions/quality | Decode cost exists before rejection; per-user upload limit helps. |
| Portable export | Authenticated Owner authorization and temporary-file cleanup | No frequency/concurrency limit; large libraries can repeatedly consume CPU, object reads and disk. |
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
- duration;
- deployment revision.

It deliberately does not include bodies, query strings, cookies,
authorization headers or raw route identifiers. Unhandled hosted errors carry
the request ID and are sent to the configured error-reporting service.

The database also stores selected security/domain events. Security events may
contain a user ID, IP address, event type and deliberately small structured
details. Maintenance currently retains these events for 180 days.

### Missing or undecided

- The API request event does not contain client IP, response size or a reason
  classification for 401/403/404/422/429.
- Caddy access logs are disabled, so static and scanner traffic is absent.
- Journald/Caddy retention and disk caps are not versioned here. Journald used
  37.7 MiB on 2026-10-14, but that observation does not prove a retention or
  maximum-disk policy.
- The proposed short retention for raw IP telemetry conflicts with the current
  180-day `security_events` retention and must be resolved in policy and code.
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
| `.env`, `.git`, WordPress and panel scans | Sensitive files are not in Caddy's static root | SPA returns 200; no Caddy visibility, scanner counter or throttling | P0 observability |
| Login brute force/account enumeration | IP + identity limits, Argon2, generic invalid-credential response | Confirmed shared Caddy-IP key; no alerting/repeat-offender policy | P0 correctness |
| Registration/recovery abuse | Invitation requirement, IP/token/email limits, generic 202 email endpoints | Confirmed shared Caddy-IP key; distributed abuse remains possible | P0 correctness |
| Forged forwarded IP | API not exposed to host | Explicit trusted-proxy configuration and spoof test absent | P0 correctness |
| Malformed request flood | Pydantic/FastAPI validation and bounded fields | No general edge limit or aggregate 422 telemetry | P1 monitor |
| Unauthorized role/ID manipulation | Server-side session, CSRF and service-layer Owner/Viewer checks | Full adversarial Owner/Viewer matrix not yet executed | P0 audit |
| Import/export exhaustion | Archive safety limits, authorization, cleanup | No per-user/library frequency or concurrency limits | P1 control |
| Health-check amplification | Separate live/ready endpoints | Ready performs dependency checks and is public/unlimited | P1 control |
| Volumetric DDoS | Caddy and small containerized surface | One VPS cannot absorb serious volumetric traffic; application limits are insufficient | P2 provider/CDN decision |

## 9. D1 closure and next PRs

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

Recommended implementation sequence:

1. **D2 proxy identity PR:** explicit trusted-proxy boundary plus spoofing and
   multi-client tests. Do not introduce IP blocking in the same PR.
2. **D3 observation PR:** privacy-filtered Caddy access events, explicit
   scanner-path responses, log rotation/retention and aggregate counters; deploy
   in observation mode.
3. **D4 limit PR:** conservative general edge limits and separate policies for
   unknown routes, auth, import/export and health. Use a shared store for any
   application-level counters.
4. **D7 abuse harness:** normal navigation, bursts, scanner paths, forged IP,
   expiry, IPv4/IPv6, secret-redaction and health-check exemptions.
5. Observe staging for at least 24 hours before enabling temporary blocking.

Numeric thresholds are intentionally not finalized in this inventory. They
must be derived from staging measurements and must have a documented rollback.
