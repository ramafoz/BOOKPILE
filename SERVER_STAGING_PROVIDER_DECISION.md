# BOOKPILE Spanish staging provider decision

Status: staging providers were purchased as an individual on 2026-09-11/13 and
are undergoing technical acceptance. Active application data stays in Spain;
encrypted operational backups and transactional-email metadata may stay in the
EU. Dinahosting manages `bookpile.gal`, its DNS and the active S3 store;
`staging.bookpile.gal` points at the isolated rehearsal VPS while the apex
remains reserved for production. No service has passed complete BOOKPILE
acceptance yet.

## Recommended rehearsal topology

| Boundary | Candidate | Why it is the current first choice |
| --- | --- | --- |
| Spanish VPS | [IONOS VPS M+](https://www.ionos.es/servidores/vps-espana) | Spain is selectable; 4 vCores, 4 GB RAM and 120 GB NVMe are advertised at a regular 9 EUR/month before VAT, with 99.99% availability, firewall and DDoS protection. This is enough for the first small PostgreSQL/Docker staging dataset without pretending it is a final capacity result. |
| Active private objects | [Dinahosting S3](https://dinahosting.com/ayuda/sincronizar-y-compartir-ficheros-con-almacenamiento-s3/) | Purchased 100 GB Spanish S3-compatible allocation, separate from the VPS, at `https://objects.dinaserver.com`. Staging uses an isolated 1 GB account and dedicated private bucket. BOOKPILE passed an authenticated round trip with signing region `us-east-1` and path-style addressing, and anonymous access was denied. A distinct read-only backup credential remains an acceptance gate. |
| Encrypted operational backups | [Backblaze B2 EU Central](https://www.backblaze.com/docs/cloud-storage-data-regions) | A third failure domain in Amsterdam. B2 supports S3-compatible per-object COMPLIANCE retention, which matches the implemented upload headers, and advertises the first 10 GB free with no minimum duration. See [Object Lock](https://www.backblaze.com/docs/cloud-storage-object-lock) and [pricing](https://www.backblaze.com/cloud-storage/pricing). |
| Transactional email | [Mailjet EU](https://www.mailjet.com/es/productos/email-api/) | Established SMTP/API delivery, EU-hosted data and an initial free level. Provider delivery, SPF, DKIM, DMARC, bounce behaviour and alerting must still pass staging. |
| Domain and DNS | Dinahosting | `bookpile.gal` was registered and `staging.bookpile.gal` points only at the isolated rehearsal host. The parked apex is not switched during 9F. |

This topology deliberately uses three infrastructure providers. The active S3
store is not a backup, and the immutable backup does not share the VPS or active
object provider. PostgreSQL initially remains on the VPS; encrypted verified
snapshots leave that host every day.

## Alternatives retained

- [Arsys VPS](https://www.arsys.es/servidores/vps/espana) keeps compute in a
  Spanish Tier III/ISO 27001 environment and offers a 4 GB / 120 GB tier, but its
  advertised regular price is higher than the equivalent initial IONOS tier.
- [Arsys Object Storage](https://www.arsys.es/cloud/object-storage) remains a
  usage-priced Spanish alternative. Its manual account validation was not
  available in time for the rehearsal and it is not part of the active path.
- [Scaleway Object Storage](https://www.scaleway.com/en/object-storage/) in
  Paris is a European backup alternative with S3 Object Lock in COMPLIANCE mode.
  Backblaze is preferred for the first rehearsal because its S3 lock example
  matches BOOKPILE's current operation and its small-volume entry cost is lower.
- IONOS Cloud Object Storage supports S3 Object Lock, but its Spanish site says
  the Cloud product is offered exclusively to professional customers. It is not
  the default until the contracting identity is known.

## Contract and technical acceptance

No candidate becomes authoritative until all applicable checks pass and the
evidence is saved without credentials:

1. Confirm contracting identity, recurring post-promotion price, VAT, minimum
   term, DPA, subprocessors, exact data region, support and complete export/
   cancellation process.
2. Provision staging-only accounts, domain, buckets and least-privilege keys.
   Production must later use different accounts or credentials, buckets,
   secrets, domains and cookie names.
3. On active S3, prove TLS/SigV4, private access, metadata preservation,
   list/get/put/delete scope, a corrupt-object rejection and an exact inventory.
4. On backup S3, create the bucket with Object Lock, upload BOOKPILE's 29-day
   COMPLIANCE objects, prove premature deletion fails, and prove lifecycle
   deletion after retention on a short-lived acceptance prefix before using the
   29-day production prefix.
5. On SMTP, prove authenticated STARTTLS, sender-domain authentication,
   idempotent retries, delayed delivery, rejection/bounce visibility and the
   terminal-failure alert route without logging recipient or message content.
6. Measure VPS free disk, memory, CPU, upload/import latency, backup duration,
   restore duration and application response times with a synthetic staging
   library. Measurements, rather than advertised capacity, set beta limits.

## Confirmed decisions

- Services are contracted as an individual.
- The VPS and active object data stay in Spain.
- Encrypted operational backups and email metadata may stay elsewhere in the
  EU.
- Dinahosting manages `bookpile.gal`; `staging.bookpile.gal` is the staging
  origin.
- Dinahosting S3 is the active-object provider; staging is capped to an isolated
  1 GB account inside the purchased 100 GB allocation. On 2026-09-13 the
  application probe verified a 1,024-byte put/stat/read/list/delete round trip,
  including integrity metadata and cleanup; an unauthenticated bucket request
  returned `403 AccessDenied`.
- IONOS hosts the Ubuntu 24.04 staging VPS in Spain at the recorded public IPv4
  address; only the DNS hostname belongs in application configuration.

The exact recurring-budget ceiling and private alert destination remain to be
confirmed before purchase and monitoring activation.

Provider selection authorizes neither production publication nor real user-data
migration. It only opens the isolated Phase 9F staging rehearsal.
