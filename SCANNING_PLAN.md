# BOOKPILE Scanning and Recognition Plan

## Purpose

Reduce manual catalogue entry by letting BOOKPILE identify a book from one of
four inputs:

1. An ISBN typed or pasted by the user.
2. A temporary photograph of the book's barcode.
3. A temporary photograph of the front cover, interpreted with OCR.
4. A live camera feed that continuously looks for a barcode.

All four methods must first check whether the identified book may already be in
the catalogue. A likely existing match should be shown to the user. If there is
no match, BOOKPILE should offer to start a new-book form with the recognized
information filled in.

This is an input aid, not an automatic catalogue writer. Nothing is created or
changed until the user reviews the result and explicitly saves a book.

## Current phase versus future metadata

The schema-v4 implementation applies field-by-field reviewed identifiers,
edition metadata, and supported classifications. Direct provider values start
selected; inferred genre, fiction category, and publication type suggestions
start unchecked. Every applied value remains editable before saving.

The lookup layer should use a future-ready result shape so it can later supply:

- ISBN-10 and ISBN-13.
- Title, subtitle, and reviewed ordered authors. Several explicit provider
  authors initialize the structured-author editor and must be checked so that
  translators, editors, and illustrators are not misclassified as authors.
- Page count, publisher, current-edition year, and language.
- Edition number, binding, and series information when explicitly available.
- Provider categories as editable genre text and cautious suggestions for
  fiction/non-fiction or publication type.
- Future structured subjects after their own migration.

Other values must not be written until their own safe incremental migrations
and reviewed form fields exist. They may be retained in the lookup response or
displayed as supporting information without being persisted.

The user's own cover photograph remains authoritative. No external cover image
will be imported. A photo used for barcode decoding or OCR is temporary and
must not become the stored cover unless a separate future action explicitly
offers that choice and the user confirms it.

## Guiding rules

- Keep manual Add Book and Batch Add fully usable if scanning, OCR, or an
  external provider is unavailable.
- Never overwrite typed form values without confirmation.
- Never modify an existing book merely because it matches a scan.
- Treat matches as warnings and choices, not hard duplicate errors; multiple
  editions or copies may be intentional.
- Keep capture, recognition, external lookup, catalogue matching, and saving as
  separate steps.
- Dispose of temporary photos and camera streams promptly.
- Keep provider credentials and provider-specific response formats out of the
  frontend.
- Preserve Batch Add's container, next position, direction, and
  collision-and-shift behaviour.
- Query configured bibliographic providers concurrently and surface usable
  field-level results progressively. Never hold the first useful answer until
  the slowest provider finishes.
- Preserve provider provenance and visible conflicts, and never overwrite a
  field the user has already edited, accepted, or deselected when a later
  provider responds.
- During one Batch Add session, carry the user's accepted-field subset forward
  as the next book's initial selection without turning it into silent saving
  or a permanent preference.

## Shared recognition and matching pipeline

Every input method should feed the same pipeline:

1. **Capture evidence**
   - Typed input produces an ISBN candidate.
   - A barcode photo or live feed produces a decoded numeric candidate.
   - Cover OCR produces recognized text and possible title/author lines.
2. **Normalize and validate**
   - Strip ISBN punctuation and spaces.
   - Validate ISBN-10 or ISBN-13 length and checksum.
   - Reject valid non-book EAN/UPC values as unsupported rather than querying
     them as ISBNs.
   - Preserve OCR's raw recognized text alongside interpreted fields.
3. **Resolve bibliographic candidates**
   - Query external providers for an ISBN.
   - For OCR, first let the user correct or map the recognized title/author;
     optionally use that text to search providers for likely editions.
   - Translate all providers into one normalized candidate format.
4. **Check the BOOKPILE catalogue**
   - Compare each candidate with existing books using the matching rules below.
5. **Present an outcome**
   - `Likely already catalogued`: show the strongest existing match and allow
     the exact record to be opened.
   - `Possible matches`: show a short list and let the user inspect or dismiss
     it.
   - `Not found in catalogue`: offer **Add to BOOKPILE**.
6. **Apply only after review**
   - Accepting an ISBN candidate copies only checked values into Add Book, Edit
     Book, or Batch Add; inferred classifications start unchecked.
   - Saving remains the existing, explicit final action.

### Common lookup result

The backend lookup adapter should return a stable result independent of the
provider. A future-ready conceptual shape is:

```text
source
source_record_id
identifiers: isbn_10, isbn_13
title
subtitle
authors[]
publisher
published_date
page_count
subjects[]
language
edition
genres[]
category
format
confidence_or_match_notes
```

Fields may be missing. Provider responses should never be treated as complete
or authoritative without user review.

## Catalogue matching

### Current matching

Schema v2 provides durable normalized ISBN-10 and ISBN-13 fields. Matching now
uses exact ISBNs first, including the ISBN-13 equivalent of a stored ISBN-10,
then falls back to these Title/Author rules:

1. Normalize case, whitespace, punctuation, and diacritics for comparison
   without changing displayed values.
2. Treat exact normalized Title plus Author as a strong match.
3. Treat exact Title with overlapping or similar Author text as a possible
   match.
4. Treat a close Title alone as a possible match, never an automatic duplicate.
5. For OCR, reduce confidence because recognition errors and omitted subtitles
   are common.

The API should return the reason and confidence class (`strong`, `possible`, or
`none`) rather than a single true/false duplicate value.

The implemented ISBN rules are:

1. Match ISBN-13 exactly first, including a normalized ISBN-10-to-ISBN-13
   comparison where possible.
2. Fall back to Title/Author matching for records without ISBNs and for OCR.
3. Keep ISBN as indexed but not necessarily unique, because a user may own two
   copies of one edition.
4. Distinguish `same ISBN already owned` from `same work, possibly another
   edition`.
5. Allow a confirmed scan to fill the reviewed form; never silently replace or
   save existing catalogue data.

## Phase 0: shared foundation

Build this once before any camera feature:

- ISBN normalization and ISBN-10/ISBN-13 checksum validation.
- A backend bibliographic lookup service with short timeouts and normalized
  errors.
- Open Library as the initial source and Google Books as fallback; return a
  small candidate list when sources or editions conflict.
- A read-only catalogue-match endpoint or service that accepts normalized
  candidate metadata and returns strong/possible matches.
- A reusable frontend result panel showing provider results, catalogue matches,
  and the actions to open an existing book or prepare a new one.
- Loading, cancellation, retry, no-result, offline, and provider-unavailable
  states that preserve all form input.
- Mocked provider tests so automated tests never depend on live third-party
  services.

No database migration is required for this foundation.

## Phase 1: typed ISBN lookup

This is the first deliverable and proves the entire lookup-and-match pipeline
without camera complexity.

### User flow

1. Open Add Book or Batch Add.
2. Type or paste an ISBN-10 or ISBN-13 and choose **Look up ISBN**.
3. BOOKPILE normalizes and validates it locally for immediate feedback, then
   sends the normalized value to the backend.
4. The backend queries the providers and returns normalized candidates.
5. BOOKPILE checks the candidates against the existing catalogue.
6. The user opens a likely existing record, selects another provider candidate,
   or chooses **Add to BOOKPILE**.
7. For a new or existing book, accepting the result fills reviewed Title,
   Author, ISBN-10, and ISBN-13 values. Nothing is persisted until the user
   submits the Add, Edit, or Batch Add form.

### Acceptance criteria

- Valid ISBN-10 and ISBN-13 examples pass; bad checksums are rejected clearly.
- Spaces, hyphens, and a terminal ISBN-10 `X` are handled correctly.
- Existing Title or Author text is not replaced without confirmation.
- Strong, possible, and no catalogue match outcomes are distinguishable.
- Provider timeout or loss of Wi-Fi leaves manual entry intact.
- Add Book and Batch Add use the same component and behaviour.
- Edit Book exposes the same stored ISBN fields and barcode/lookup tools.
- Stored ISBNs are normalized, searchable, and used for exact catalogue
  matching while intentional duplicate copies remain allowed.

## Phase 2: barcode from a temporary phone photo

Add a mobile-friendly **Photograph barcode** action that decodes an ISBN and
passes it into Phase 1.

### Technical approach

- Use a file input with mobile camera capture support so the current HTTP local
  network setup remains usable.
- Decode in the browser where practical, using a maintained barcode library
  such as ZXing's browser package.
- Prioritize EAN-13 book barcodes and validate the decoded digits as an ISBN.
- Feature-detect native barcode support only as an optimization; do not make it
  a requirement.
- Revoke image object URLs, release image data, and clear the input after
  decoding or cancellation.
- Do not upload, save, back up, or reuse the barcode photograph as a cover.

If browser-side decoding proves unreliable on the actual phone, a backend
decoder can be evaluated as a fallback. In that case, enforce image type and
size limits and delete temporary server files in all success and error paths.

### User flow

1. Tap **Photograph barcode**.
2. Take or choose a clear photograph.
3. BOOKPILE decodes one or more barcode candidates.
4. If exactly one valid ISBN is found, continue through Phase 1 automatically.
5. If several valid ISBNs are found, ask the user to choose one.
6. If none is found, offer Retake, Type ISBN, Cover OCR, or Manual entry.

### Acceptance criteria

- Works from the phone over BOOKPILE's current Wi-Fi URL without HTTPS.
- Handles rotated, cropped, moderately blurred, and high-resolution photos
  within a documented practical limit.
- Rejects non-book barcodes with a useful message.
- Never changes the stored cover or leaves a temporary image behind.
- A failed decode does not clear form or Batch Add state.

## Phase 3: optional OCR from a temporary cover photo

OCR is the final current-database capture method. It is a fallback for books
whose barcode is missing, damaged, or not useful. It should be explicitly
optional because it is slower and less deterministic than ISBN lookup.

### Initial OCR design

- Run OCR in the browser where practical, for example with Tesseract.js, so the
  cover image normally remains on the phone.
- Start with the languages actually needed by this library and load language
  data on demand; show download/progress and allow cancellation.
- Preserve word/line bounding information when available, not only plain text.
- Show the recognized lines and let the user explicitly assign or edit Title
  and Author. Do not assume that the largest text is always the title or that
  every cover displays the author's name clearly.
- After user correction, optionally search bibliographic providers by
  Title/Author and show edition candidates.
- Run the same catalogue matcher before offering addition.
- Discard the temporary OCR image and keep stored cover capture as a separate
  user-controlled step.

An early useful version does not need an AI model: line selection, simple
layout heuristics, normalization, provider search, and user confirmation are
safer than silently interpreting arbitrary cover designs. More advanced OCR or
language models can be evaluated later behind the same result contract.

### User flow

1. Tap **Read cover text** and take or choose a front-cover photograph.
2. See OCR progress, then the recognized text lines.
3. Select/edit the proposed Title and Author.
4. Optionally search external providers for a cleaner bibliographic candidate.
5. Review possible existing BOOKPILE matches.
6. Open an existing record or apply Title and Author to the add form.

### Acceptance criteria

- OCR can be cancelled and never blocks manual entry.
- The user can correct every recognized value before lookup or application.
- Poor confidence is communicated; no raw OCR result is auto-saved.
- Covers with multiple languages, subtitles, contributor names, or no visible
  author fail gracefully into manual selection/editing.
- Temporary images are discarded and never silently become stored covers.

## Phase 4: future live camera barcode scanning

Live continuous scanning remains a desirable future mode, not a prerequisite
for Phases 1-3.

The current mobile URL is served from another machine over local-network HTTP.
Browser camera streams exposed through `getUserMedia()` require a secure
context in modern browser standards, so this phase needs a deployment decision
before implementation: provide trusted local HTTPS, package BOOKPILE as an
installable/native app, or use another secure origin. `localhost` exceptions on
the server computer do not solve access from a phone using the computer's LAN
address.

### Feasibility gate

Before building the UI:

- Choose and test a trusted-HTTPS approach on the actual phone and desktop.
- Confirm iOS Safari and/or Android Chrome camera permission behaviour.
- Confirm that the certificate can be trusted without making normal BOOKPILE
  startup fragile.
- Keep temporary-photo and typed-ISBN flows as permanent fallbacks.

### Intended live flow

1. Open **Scan live** and explicitly grant camera permission.
2. Prefer the rear camera and show a barcode guide.
3. Decode frames using a proven stream-capable library such as ZXing, with
   native `BarcodeDetector` only when feature detection confirms support.
4. Debounce repeated detections of the same code.
5. Freeze on a valid ISBN and pass it through the shared Phase 1 pipeline.
6. Offer **Scan next** in Batch Add.
7. Stop every media track on success, close, navigation away, permission error,
   or page backgrounding.

Optional torch, focus, and zoom controls should be capability-detected rather
than assumed.

### Acceptance criteria

- No camera starts before an explicit user action.
- Permission denial has a clear fallback to photo or typed ISBN.
- Streams and camera indicators stop reliably whenever the scanner closes.
- Repeated frame detections trigger only one lookup.
- Batch Add can scan several books consecutively without losing location or
  position state.

## Batch Add integration

All available capture methods should appear in Batch Add without altering its
physical-cataloguing behaviour:

1. Enter Batch Add and choose a container, starting position, and direction.
2. Choose Type ISBN, Photograph barcode, or—after Phase 3—Read cover text.
3. Resolve external candidates and existing catalogue matches.
4. If adding, review/correct Title, Author, and ISBN fields and take the user's
   own stored cover photo separately.
5. Save through the existing collision-and-shift rules.
6. Preserve container and direction, advance the position, and clear
   book-specific values.
7. Return focus to the previous capture method for the next book.

An existing-book match must not advance Batch Add's position because no new
book has been saved.

## Error and edge cases

- Valid ISBN with no provider result: keep the ISBN visible for correction and
  allow manual entry.
- Conflicting provider editions: show candidates instead of silently merging.
- Incomplete provider data: apply only reliable, user-selected values.
- Several catalogue matches: show all plausible records and allow intentional
  addition.
- Network unavailable: skip external lookup but preserve recognized evidence
  and all form state.
- Multiple barcodes in one image: ask the user to choose or retake.
- OCR false positive: retain raw lines and allow complete manual correction.
- Intentional duplicate copy: warn, then allow the normal explicit add flow.

## Verification strategy

### Unit and backend tests

- ISBN normalization, conversion where applicable, and checksum fixtures.
- Provider success, fallback, conflict, incomplete data, timeout, malformed
  response, and no-result cases using mocks.
- Catalogue normalization and strong/possible/no-match fixtures, including
  punctuation, accents, subtitles, and multiple-author text.
- Confirmation that lookup and matching endpoints perform no database writes.

### Frontend tests

- Accept, reject, edit, retry, cancel, and preserve pre-existing text.
- Existing-match and add-new branches.
- Temporary-image cleanup and camera-stream cleanup.
- Batch Add state preservation in ascending and descending modes.
- Accessibility for keyboard, screen-reader labels, focus return, and status
  announcements.

### Device tests

- Test the real Wi-Fi workflow on the intended phone/browser.
- Use a representative set of ISBN-10, ISBN-13, supplemental-price barcodes,
  damaged labels, glossy covers, rotated photos, and multilingual covers.
- Measure decode/OCR time and memory on the phone, not only desktop.
- For Phase 4, test permission grant, denial, revocation, backgrounding, and
  repeated consecutive scans over trusted HTTPS.

## Recommended delivery order

1. Shared foundation, including catalogue matching and the reusable
   existing/new-book decision UI.
2. Typed ISBN lookup end to end.
3. Temporary-photo barcode decoding.
4. Batch Add integration and real-device hardening.
5. Optional cover OCR.
6. Safe schema expansion and persistence of richer metadata when separately
   approved.
7. Live camera scanning after the HTTPS feasibility gate.

Each numbered step should be releasable without requiring the next one.

## Relative implementation difficulty

- **Shared foundation and typed ISBN: medium.** The individual algorithms are
  straightforward; most of the work is reliable provider handling, cautious
  catalogue matching, and review UI.
- **Temporary-photo barcode: medium.** The library integration is contained,
  but real-device image quality and browser memory need practical testing.
- **Cover OCR: medium-high.** OCR itself is available, but converting arbitrary
  cover layouts into trustworthy Title/Author suggestions requires careful
  interaction design and multilingual testing.
- **Live camera barcode: high.** Frame decoding is feasible; trusted HTTPS,
  phone/browser compatibility, permissions, and reliable stream cleanup make
  this an infrastructure and device-support phase as well as a scanner feature.

## Primary technical references

- [Open Library Search API](https://openlibrary.org/dev/docs/api/search)
- [Open Library ISBN/data APIs](https://openlibrary.org/dev/docs/json_api)
- [Google Books API](https://developers.google.com/books/docs/v1/using)
- [ZXing browser library](https://github.com/zxing-js/browser)
- [Tesseract.js](https://github.com/naptha/tesseract.js/)
- [W3C Media Capture and Streams](https://w3c.github.io/mediacapture-main/)
- [Barcode Detection API proposal](https://wicg.github.io/shape-detection-api/)
