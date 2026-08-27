# BOOKPILE Local v1 limitations

BOOKPILE Local v1 intentionally has a narrow deployment model.

- It is a single-user, local-first Windows application.
- It has no accounts, permissions, collaboration, public profiles, or cloud
  synchronization.
- Its LAN address is intended only for trusted devices on the same private
  network. It is not hardened or packaged for direct internet exposure.
- It uses local HTTP rather than trusted HTTPS. Continuous live-camera barcode
  scanning is therefore not included; temporary barcode photographs and cover
  OCR are available.
- ISBN metadata depends on external bibliographic services and may be slow,
  incomplete, inconsistent, or temporarily unavailable. All retrieved values
  require user review.
- OCR accuracy depends heavily on cover typography, lighting, language, and
  image quality.
- Goodreads links and bibliographic metadata remain user-maintained.
- Cover images and backups consume local disk space. There is no automatic
  off-device backup.
- The application interface and release documentation are English-only in
  v1.0. Multilingual Local and Server interfaces are planned as later work.
- CSV files are exports, not restorable backups.
- A full restore replaces the current catalogue rather than merging records.
- The future hosted multi-user product is a separate edition. A Local full ZIP
  is intended to become its migration input; the Local application itself will
  not be converted into a switchable server edition.

The authoritative future roadmap is maintained in [TODO.md](TODO.md).
