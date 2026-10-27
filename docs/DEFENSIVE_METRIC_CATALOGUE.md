# BOOKPILE defensive metric catalogue

This is the binding field and source contract for D5 aggregate detection. Work
status, alert acceptance and production gates live only in
`BOOKPILE_MASTER_WORK_PLAN.md`.

## Collection contract

The host collector runs every 15 minutes over the immediately preceding
15-minute window. It emits one JSON document to the root-owned system journal.
Every metric contains only a fixed policy name, a route template or bounded
security scope, an exact deployment revision and integer totals. Groups with no
events are represented by a zero total and an empty group list.

The collector must fail closed when a source is unavailable or malformed. It
must never emit a raw or keyed client address, user/library/object identifier,
request URL or query, header, cookie, body, validation value, catalogue value,
exception text or arbitrary database event detail.

| Metric | Source | Meaning |
| --- | --- | --- |
| `http_429` | API request journal | Responses rejected by an application request limit. |
| `http_503` | API request journal | Requests for which BOOKPILE could not make a required safe decision or reach a required dependency. |
| `http_5xx` | API request journal | All server-error responses, including the `503` subset. |
| `lease_conflicts` | PostgreSQL `security_events` | Observed or enforced conflicting costly-operation leases, grouped by event type and lease scope. |
| `scanner_probes` | Caddy minimized access log | Requests matched by the narrow, fixed scanner-probe policy. |
| `temporary_bans` | Caddy minimized access log | Edge ban actions once D6 supplies them. A zero before D6 does not claim that bans exist. |
| `repeated_validation_failures` | API request journal | `422` responses from a keyed client reaching at least five failures on one route template in the window. Output contains only event and repeated-client totals, never the key. |

`503` is intentionally also counted in `5xx`; these are two views of the same
event, not additive totals. Scanner and future ban events carry their deployed
revision at event creation so a collection window spanning a deployment cannot
misattribute old evidence to the new image.

Warning/critical thresholds, notification routing, deduplication, recovery and
ownership are the next D5 gate and are deliberately not defined by this
source contract.
