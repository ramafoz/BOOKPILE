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

## Alert contract

Every successful collection is evaluated as one 15-minute incident window.
All anomalous metric families in that window are grouped into one overall
severity; `critical` wins over `warning`. Exact inclusive thresholds are:

| Metric | Warning | Critical | Reason |
| --- | ---: | ---: | --- |
| `http_429` | 25 | 100 | Detect sustained application-limit pressure without paging for an isolated rejected retry. |
| `http_503` | 1 | 5 | One fail-closed dependency or decision failure needs review; five indicate active service degradation. |
| `http_5xx` | 5 | 20 | Group sporadic server faults separately from a sustained failure burst. The `503` subset is not added twice. |
| `lease_conflicts` | 1 | 5 | A costly-operation collision is unusual in the beta and must be reviewed. |
| `scanner_probes` | 10 | 60 | Ignore isolated Internet background noise while detecting a deliberate scanner burst. |
| `temporary_bans` | 1 | 5 | Every future D6 ban is significant; five in one window are critical. A pre-D6 zero remains normal. |
| `repeated_validation_failures` | 10 | 25 | Detect repeated malformed use after the five-per-client qualification without alerting on normal form correction. |

The current destination is two dedicated Healthchecks checks,
`BOOKPILE staging - D5 warning` and `BOOKPILE staging - D5 critical`, both
routed to the separately verified operator mailbox. They use the same
`4,19,34,49 * * * *` UTC schedule as the collector and ten minutes of grace.
The responsible owner is
the designated BOOKPILE platform operator: acknowledge a warning within four
hours and a critical alert within 30 minutes. If there is no available owner,
production must remain closed.

Every run sends one explicit success or failure signal to each channel. Only
the channel matching the current overall severity fails; the other succeeds.
Healthchecks sends mail on the resulting status transition, deduplicates
repeated failure signals while the check remains down, and sends recovery when
it receives success. Missing pings also alert after grace, covering collector,
evaluator, timer or host failure. Notification bodies contain only metric
names, aggregate totals, fixed thresholds, severity and UTC time.
