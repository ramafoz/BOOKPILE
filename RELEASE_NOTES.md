# BOOKPILE Local v1.0.0

BOOKPILE Local v1.0.0 is the first packaged single-user release of the personal
library manager. It runs on a Windows computer and can be used from trusted
devices on the same private Wi-Fi.

## Highlights

- Rich personal catalogue with covers, identifiers, edition metadata,
  structured multiple authors, dates, notes, status, and physical position.
- Historical reading sessions and re-reading, personal reading statistics,
  and reading suggestions.
- Loan and return history without losing shelf positions.
- Full-screen visual library map with touch/mouse navigation, metadata colour
  modes, inspection, layout editing, and atomic physical rearrangement.
- ISBN lookup, temporary barcode photographs, and optional cover OCR.
- Verified full ZIP backup/restore with checksums, safety backups, rollback,
  and separate CSV exports.
- Guided Windows installer plus Start/Stop desktop shortcuts.

## Data compatibility

The release uses database schema v8 and full backup format v1. A full Local ZIP
contains the database and every referenced cover and is the planned migration
input for the future hosted Server edition. CSV exports cannot be restored.

## Important limitations

Local v1 has no accounts or network access controls and must never be exposed
directly to the internet. It is English-only and Windows-only, and it does not
provide cloud synchronization or automatic off-device backups. See
[LIMITATIONS.md](LIMITATIONS.md) before installing.

## Installation

Read [INSTALLATION.md](INSTALLATION.md). Python 3.11+ and Node.js 20+ are
required during installation. Keep a full ZIP backup outside the application
folder before any update.

## Licence

BOOKPILE is free software under `AGPL-3.0-or-later`, copyright © 2026 Javier
Ramalleira Fernández. Modified versions offered over a network remain subject
to the source-availability requirements of that licence. See `LICENSE` and
`COPYRIGHT` in the release.
