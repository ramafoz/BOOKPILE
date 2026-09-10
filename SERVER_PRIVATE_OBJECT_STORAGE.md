# BOOKPILE Server private object storage

## Boundary

BOOKPILE stores cover and profile-image bytes behind one internal interface.
PostgreSQL remains authoritative for each opaque key, byte count and SHA-256.
Browsers never receive a bucket key, bucket URL or storage credential: they
request an authenticated BOOKPILE API route, exactly as with filesystem storage.

Development defaults to `filesystem`. Hosted startup fails unless `s3` is
selected and a region, private bucket, HTTPS endpoint, access key, secret key
and safe deployment prefix are all explicit. Connection/read timeouts, retries,
pool size and addressing style are bounded configuration.

The S3 adapter:

- never supplies a public ACL or produces presigned browser URLs;
- puts every object below the environment-specific prefix;
- records a SHA-256 in private object metadata;
- verifies metadata, size and downloaded bytes after every write;
- reads remote bodies in bounded chunks and rejects missing/wrong checksums;
- treats deletion as idempotent;
- exposes bucket readiness and a fully verified inventory.

## Provider acceptance contract

Do not insert production credentials until a provider has passed all of these:

- contractual data location and processing in Spain or the explicitly approved
  EU region, with DPA, subprocessors and exit/export terms reviewed;
- HTTPS endpoint, S3 v4 signatures and the configured addressing style;
- bucket is private, has no static website, public policy or anonymous access;
- a dedicated service credential can only list the selected prefix and get,
  put and delete objects below it; it cannot administer users or other buckets;
- encryption at rest, versioning/lifecycle behaviour, egress, request pricing,
  capacity and support are documented;
- provider-side retention does not violate BOOKPILE account/library deletion
  windows or the later Phase 9D backup policy.

Use separate bucket/prefix credentials for staging and production. Never test
production credentials from CI, Local or a developer workstation.

## Audit command

The installed command compares PostgreSQL with the selected adapter:

```bash
bookpile-private-objects audit
```

Exit 0 means exact. Exit 1 means missing, orphaned or mismatched objects. Output
contains counts and short hashes of opaque keys, never raw keys, credentials or
personal data. An anomaly is evidence to investigate; audit never deletes.

## Filesystem-to-S3 migration

Migration is copy-then-verify and is intentionally not an automatic startup
step. It never deletes the filesystem source and never switches a running API.

1. Stop API writes and take a verified database/filesystem backup.
2. Configure the future S3 adapter and retain the old filesystem root at
   `BOOKPILE_SERVER_PRIVATE_OBJECT_ROOT`.
3. Run the read-only plan:

   ```bash
   bookpile-private-objects migrate-from-filesystem
   ```

4. Resolve every missing/mismatched source object before continuing.
5. Copy and verify:

   ```bash
   bookpile-private-objects migrate-from-filesystem --apply
   bookpile-private-objects audit
   ```

6. Only after an exact audit, start the API with `PRIVATE_OBJECT_BACKEND=s3` and
   smoke-test authenticated cover/profile reads and a replace/delete cycle.
7. Retain the protected filesystem copy through the agreed rollback window.
   Remove it only under the later backup/retention procedure.

The operation is restartable: already matching targets are downloaded and
verified, then skipped. A partial target is never made authoritative merely
because some copies succeeded. Unexpected target orphans fail final validation
and are not deleted automatically.

## Current acceptance boundary

The adapter, configuration, compensation contract, corruption tests, dry-run /
apply migration and inventory reconciliation are implemented. Phase 9B is not
formally closed until the chosen provider passes an isolated real-bucket round
trip and the complete development inventory is migrated/reconciled in staging.

