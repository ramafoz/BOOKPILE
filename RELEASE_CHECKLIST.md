# BOOKPILE Local v1 release checklist

No public tag or GitHub release should be created until every blocking item is
complete and the release candidate has explicit user approval.

## Repository and data safety

- [x] Work from `release/local-v1`, based on the accepted `main` history.
- [x] Confirm the live working tree was clean before release preparation.
- [x] Create and validate a full pre-release ZIP outside Git.
- [x] Confirm the pre-release backup is schema v8 and contains 434 books and
  434 covers with valid checksums, database integrity, and foreign keys.
- [x] Add `AGPL-3.0-or-later` and the copyright notice for Javier Ramalleira
  Fernández.
- [x] Review the final Git diff and commit the release candidate.

## Automated verification

- [x] Backend test suite passes.
- [x] Frontend unit tests pass.
- [x] Frontend lint passes.
- [x] Optimized frontend build passes.
- [x] PowerShell release scripts parse without errors.
- [x] Clean-copy installer creates private dependencies and a fresh database.
- [x] Fresh database is identified as schema v8, empty, and internally valid.
- [x] Isolated backend health, empty books, and empty statistics pass.
- [x] Isolated optimized frontend returns HTTP 200.
- [x] Full ZIP restoration into the isolated installation preserves all source
  counts, covers, schema v8, integrity, and foreign keys and creates a safety
  backup first.
- [x] Re-running the installer over that restored isolated installation keeps
  all 434 books and 434 cover references intact.
- [ ] Build the committed release ZIP and SHA-256 file from the final tag.
- [ ] Extract that exact artifact into another clean folder and repeat the
  installer/start smoke test.

## Manual acceptance

- [ ] Install the candidate using only `INSTALLATION.md`.
- [ ] Confirm Start and Stop desktop shortcuts on Windows.
- [ ] Confirm catalogue use on the host browser.
- [ ] Confirm phone/tablet access over trusted private Wi-Fi.
- [ ] Create a small disposable bookcase/shelf/container/book sequence.
- [ ] Exercise cover upload, ISBN lookup, barcode photo, and optional OCR.
- [ ] Exercise reading, re-reading, loan, map inspection, and rearrangement.
- [ ] Download and validate a full backup from the candidate.
- [ ] Restore that candidate backup into a disposable isolated installation.
- [ ] Confirm documentation is understandable and limitations are visible.
- [ ] Receive explicit approval to publish Local v1.0.0.

## Publication

- [ ] Merge or fast-forward the approved release work according to the chosen
  maintenance policy.
- [ ] Create the annotated `v1.0.0` tag at the approved commit.
- [ ] Push the release branch and tag.
- [ ] Publish `BOOKPILE-Local-v1.0.0.zip`, its `.sha256`, and release notes on
  GitHub.
- [ ] Preserve `release/local-v1` for critical Local fixes.
- [ ] Create the separate multi-user foundation branch only after Local v1 is
  recoverable from its public tag and artifact.
