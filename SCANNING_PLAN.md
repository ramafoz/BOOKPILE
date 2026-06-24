# BOOKPILE Scanning Plan

## Scope

This feature is deliberately limited to reducing manual typing while adding
books. Scanning will suggest only:

- Title.
- Author.

The user will continue taking and storing their own cover photographs.
BOOKPILE will not import cover images, page counts, subjects, publishers,
publication dates, editions, genres, or other external metadata.

OCR is outside the current scope and may be considered later for books without
a usable ISBN or barcode.

## Guiding rules

- Scanning is an input aid, never an automatic catalogue write.
- The user must review the proposed title and author before saving.
- Existing typed values must not be overwritten without confirmation.
- External lookup failures must leave normal manual entry fully usable.
- No existing book or cover data may be modified by a lookup.
- ISBN lookup and barcode decoding should be separable so either can be used
  independently.

## Phase 1: ISBN lookup

Add an ISBN lookup control to both normal Add Book and Batch Add.

### Intended flow

1. The user types or pastes an ISBN-10 or ISBN-13.
2. BOOKPILE validates and normalizes the value.
3. The backend queries Open Library.
4. If no useful result is found, it queries Google Books as a fallback.
5. BOOKPILE displays the proposed title and author.
6. The user accepts, edits, or rejects the proposal.
7. Accepting fills only the Title and Author fields.

If sources return ambiguous or conflicting editions, the interface should show
a small candidate list instead of silently choosing one.

### Data model

For the first version, the ISBN is transient lookup input and does not need to
be stored in the database. Storing ISBNs can be reconsidered later if duplicate
detection or edition tracking becomes desirable.

### Backend responsibilities

- Normalize ISBN input.
- Validate ISBN-10 and ISBN-13 checksums.
- Query external providers with short timeouts.
- Translate provider-specific responses into a small common result:
  `title`, `author`, `source`, and optionally the normalized ISBN.
- Return clear not-found and provider-unavailable responses.
- Avoid exposing provider credentials to the frontend.

## Phase 2: barcode capture and Batch Add integration

Decode the EAN-13/ISBN barcode from the phone and pass the detected ISBN into
the Phase 1 lookup.

### Initial capture method

Prioritize a mobile-friendly **photograph barcode** control. The user takes or
selects a photo, BOOKPILE decodes it, and the image is discarded after
decoding. It must not replace or become the book's cover photograph.

This approach is compatible with the existing local-network workflow. Direct
live camera APIs generally require HTTPS on mobile browsers, whereas an image
file input can invoke the phone camera without changing BOOKPILE's current
server setup.

Live continuous scanning can be added later if local HTTPS is introduced.

### Batch Add flow

1. Enter Batch Add and choose a physical container.
2. BOOKPILE keeps that container and suggests the next position, as it does
   today.
3. Tap **Scan ISBN**.
4. Photograph the barcode.
5. Decode and look up the ISBN.
6. Review or correct Title and Author.
7. Take the user's own cover photograph using the existing cover control.
8. Save the book.
9. Preserve the container, advance the position, clear book-specific fields,
   and make scanning immediately available for the next book.

The scanner must not disrupt the existing collision-and-shift workflow for
inserting a book into an occupied physical position.

## Error and edge cases

- Invalid or partially visible barcode: invite another photo or manual ISBN.
- Valid barcode with no provider result: retain the ISBN and allow manual
  Title and Author entry.
- Multiple barcodes in one image: ask the user to select or retake the photo.
- Duplicate scan during Batch Add: warn without blocking intentional duplicate
  editions or copies.
- Network unavailable: fail quickly and keep the add form intact.
- Provider returns incomplete information: fill only reliable fields and leave
  the rest editable.
- Non-book EAN barcode: report that no ISBN was detected.

## Verification

- Unit tests for ISBN normalization and checksums.
- Backend tests for provider success, fallback, timeout, malformed data, and
  no-result cases using mocked responses.
- Frontend tests for accepting, rejecting, and preserving existing field text.
- Mobile tests on the actual Wi-Fi workflow and the intended phone/browser.
- Batch Add test covering several consecutive scans in one container.
- Regression tests confirming that covers and existing catalogue records are
  untouched.

## Deferred ideas

- OCR from front covers.
- Live continuous camera scanning over HTTPS.
- Persisting ISBNs for duplicate detection and edition management.
- Importing external covers or additional bibliographic metadata.
