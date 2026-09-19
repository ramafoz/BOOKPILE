# ADR 0014: Encrypted off-site operational recovery

## Decision

Server operational recovery uses PostgreSQL custom dumps and referenced private
objects, encrypted before leaving a dedicated non-root backup process. Backups
use a bucket and credentials separate from active objects. The API and email
worker do not receive the backup encryption key or destination credentials.

A plaintext completion marker is written only after all encrypted artefacts and
the encrypted manifest are verified. Production requires bucket versioning and
S3 Object Lock compliance retention. Restore is permitted only into an empty
database and empty object store and PostgreSQL restore is one transaction.

Snapshots are retained for 29 days under a daily schedule, leaving operational
margin beneath the 30-day deleted-data ceiling. Encryption keys are externally
custodied and identified, not embedded in snapshots.

## Consequences

- User ZIPs remain portability products, not disaster recovery.
- A total application-host loss does not destroy the only backup.
- Compromise of the API process does not directly reveal backup credentials.
- Cross-service restoration cannot be perfectly atomic, so failed targets are
  discarded and recreated; they are never promoted before invariant checks.
- Provider Object Lock, lifecycle and restore behaviour require staging proof.
