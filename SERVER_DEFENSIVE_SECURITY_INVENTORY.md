# BOOKPILE Server defensive-security inventory

Status: initial code-backed inventory, 2026-10-14. This document records what
the versioned staging/production stack does today. Items marked **prove on
staging** must not be treated as controls until runtime evidence exists.

## 1. Trust boundaries and exposed services

| Boundary | Current control | Evidence | Remaining work |
| --- | --- | --- | --- |
| Internet to host | The accepted IONOS IPv4 firewall permits only TCP 22, 80 and 443; staging has no global IPv6 address or `AAAA` record | `SERVER_STAGING_PROVISIONING_CHECKLIST.md` and `SERVER_OPERATIONS_AND_SECURITY.md`; listener freshness rechecked 2026-10-14 | Recheck after firewall, DNS or network changes; do not treat inactive UFW as the control. |
| Caddy to API | API has no host `ports`; Caddy reaches `api:8100` on the internal `backend` network | Compose, `server/docker/Caddyfile`, accepted 2026-09-16 evidence and 2026-10-14 `ss`/Compose recheck | Add an automated regression assertion; no new staging acceptance is required. |
| API/worker to PostgreSQL | PostgreSQL has no host `ports` and `backend` is `internal: true` | Compose | Retain this design and test it in the production checklist. |
| API/worker to Internet | Explicit `egress` network | Compose | Document required destinations; unrestricted outbound traffic is not yet an application firewall. |
| Browser to API | Same-origin HTTPS, opaque HttpOnly session cookie, double-submit CSRF token, hosted secure-cookie validation | Auth routes, dependencies and settings | Exercise cross-origin and forged-CSRF cases in the final audit. |
| Host headers and API docs | Trusted-host middleware; wildcard hosts and hosted API docs are rejected | `main.py` and `config.py` | Verify effective staging values. |

The containers run as non-root and the API, worker and web filesystems are
read-only. The API has a 64 MiB temporary filesystem. These are useful blast-
radius controls, not request-abuse controls.

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

Therefore the effective client identity is **not yet proven**. It may be the
Caddy container address rather than the Internet client address. Blindly
trusting `*` would fix attribution but would make spoofing possible if the API
were ever reached through another path.

Required proof before adding IP blocking:

1. Record the effective Uvicorn forwarded-header configuration.
2. Send two requests from distinct known client addresses and show distinct
   `request.client.host` values without retaining unrelated personal data.
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
| Login brute force/account enumeration | IP + identity limits, Argon2, generic invalid-credential response | IP identity unproven; no alerting/repeat-offender policy | P0 correctness |
| Registration/recovery abuse | Invitation requirement, IP/token/email limits, generic 202 email endpoints | IP identity unproven; distributed abuse remains possible | P0 correctness |
| Forged forwarded IP | API not exposed to host | Explicit trusted-proxy configuration and spoof test absent | P0 correctness |
| Malformed request flood | Pydantic/FastAPI validation and bounded fields | No general edge limit or aggregate 422 telemetry | P1 monitor |
| Unauthorized role/ID manipulation | Server-side session, CSRF and service-layer Owner/Viewer checks | Full adversarial Owner/Viewer matrix not yet executed | P0 audit |
| Import/export exhaustion | Archive safety limits, authorization, cleanup | No per-user/library frequency or concurrency limits | P1 control |
| Health-check amplification | Separate live/ready endpoints | Ready performs dependency checks and is public/unlimited | P1 control |
| Volumetric DDoS | Caddy and small containerized surface | One VPS cannot absorb serious volumetric traffic; application limits are insufficient | P2 provider/CDN decision |

## 9. D1 closure criteria and next PRs

D1 is complete when the following evidence is attached to this inventory:

- effective Caddy and Uvicorn proxy-header configuration;
- genuine and forged client-IP test results;
- representative response evidence for 401, 403, API 404, SPA fallback,
  422 and 429;
- effective journald retention/disk policy;
- decision on raw-IP purpose and retention.

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
