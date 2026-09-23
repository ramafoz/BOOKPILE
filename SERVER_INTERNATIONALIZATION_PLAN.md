# BOOKPILE Server internationalization

The private-beta launch targets English (`en`), Galician (`gl`), Spanish (`es`),
Basque (`eu`), Catalan/Valencian (`ca`), Aranese Occitan (`oc-ES`), Portuguese
(`pt`), Italian (`it`), French (`fr`), and Simplified Chinese (`zh-Hans`). The
selector presents Catalan and Valencian together as `Català / Valencià`; BOOKPILE
maintains one reviewed catalogue for them. German, Japanese, Dutch, Greek,
Arabic and Korean are post-launch candidates and must not appear as selectable
languages until their routes are complete. Arabic additionally requires a full
right-to-left layout and interaction audit. Language of the interface is
independent of a book's bibliographic language. English is the source catalogue
and fallback.

## Delivery slices

- [x] Establish typed message catalogues, locale resolution, browser preference,
  document language and regional formatting. Make only complete locales
  selectable; do not present untranslated pages as translated.
- [x] Translate the entire unauthenticated account journey: invitation signup,
  verification, sign-in, reset and deletion recovery. Preserve generic responses
  that avoid account enumeration. Localize safe API error codes, never raw server
  exception text.
- [ ] Translate the authenticated shell, account and library controls, catalogue,
  map, statistics, readings, loans, imports/exports, dialogs and notices. Audit
  screen-reader labels, empty states and mobile widths for longer strings.
- [x] Persist the account preference server-side for cross-device use. Before
  sign-in, use a best-effort browser preference; define precedence and a
  privacy-safe API migration. Browser storage must not contain tokens.
- [ ] Localize every transactional email in text and HTML, using the account
  preference captured when the message is queued. Keep subject, action and
  expiry copy consistent, and preserve SMTP/DKIM behavior and privacy rules.
- [ ] Add the remaining eight launch locales in reviewed batches; verify plural rules,
  dates, numbers and relative time with `Intl`, plus typography and CJK font
  fallback. User-generated names and book metadata are never machine-translated.
- [ ] Run end-to-end language switching, reload, fresh browser, cross-device,
  auth links, email, accessibility and mobile tests before beta acceptance.

Do not expose a locale in the selector until its current route is covered. A
feature branch may contain a partial migration; staging promotion waits for a
coherent full-user journey.

## Language choices and precedence

- The public home page must offer a visible language selector. The pre-sign-in
  Server home/account shell already has one for English and Galician; extend
  the same choice to the eventual production landing page. Before sign-in,
  prefer an explicit browser-stored choice, then a supported browser language,
  then English. Do not infer language from a book's metadata or IP address.
- Each account has its own preferred locale. Registration records the language
  chosen on the sign-up page; existing accounts migrate to English. Once the
  authenticated workspace is translated, sign-in and `/auth/me` should apply
  the account preference across devices. Changing it in the personal account
  page must save it server-side; that account setting must not be confused with
  a library-wide setting. The API field and protected update endpoint can be
  introduced before the unfinished workspace is exposed in Galician.
- For both account and library invitations, the inviter chooses the language
  of a predefined message independently of their own account preference. No
  automated email is required: show the message with its invitation URL and
  offer separate actions to copy the whole message or just the URL. The text
  must distinguish catalogue/map viewing from equal co-Owner authority; it
  must not imply the recipient already has a BOOKPILE account. Keep the chosen
  language with the generated invitation presentation, without changing the
  inviter's preference. A recipient may choose a different language during
  registration or acceptance. Do not put an invitation token in logs or
  analytics. Existing flows generate links/tokens only; message composition
  and its copy controls are implemented for English and Galician.
- Account-action emails (verification, password reset, deletion recovery) use
  the recipient account preference captured at queue time, not an inviter's
  choice. The existing outbox encrypts the rendered subject, text and HTML, so
  retries keep the same language even if the preference changes later.
  Unknown-account responses remain generic in every language.

## First branch checkpoint

`feature/server-i18n-foundation` adds typed English/Galician catalogues,
browser-locale detection and persistence, an accessible account-flow selector,
`Intl` formatting helpers, and translated static copy for the unauthenticated
routes. The signed-in workspace deliberately remains English and reports
`lang="en"`. Generic localized authentication errors avoid exposing raw API
details; a later slice should introduce stable, localized error codes and
review form validation. Catalogues now live in one module per language; adding
another locale requires a complete key set and matching interpolation variables
before it can appear in the selector. This checkpoint is not the multilingual
beta.

## Second branch checkpoint

Migration `0023_account_locale` adds a non-null English default for existing
accounts. Registration accepts only `en` or `gl` and saves the sign-up choice;
login, session rotation and `/auth/me` return it. An authenticated, CSRF-protected
`PUT /auth/locale` updates it. The frontend API knows this contract, but the
authenticated language control and preference hydration wait for complete
workspace translations. Invitation message composition is not implemented.

## Third branch checkpoint

The three transactional account emails have reviewed English and Galician
subject, text and HTML copy. They render from the recipient's account locale
before entering the encrypted outbox; the HTML `lang` attribute follows the
message. Token lifetimes, URLs, privacy-safe responses and transport are
unchanged. Invitation message composition remains a separate feature with a
per-invitation language choice; it does not require sending email.

## Fourth branch checkpoint

Account and library invitations now compose reviewed English or Galician copy
without sending email. The inviter can copy the complete message or only its
single-use URL. Library copy truthfully distinguishes catalogue-only access,
catalogue-and-map access and equal co-Owner authority. The generated role,
scope and library name are snapshotted with the displayed link so later form
changes cannot misdescribe an existing token; changing the message language
does not alter either user's account preference.

## Fifth branch checkpoint

Successful login and `/auth/me` now hydrate the browser locale from the account
preference, which therefore follows the user across devices and remains the
pre-sign-in choice after logout. The personal account page can update the
preference through the protected API and explains that invitation language is
independent. The authenticated workspace deliberately continues to declare
English until all of its sections have complete Galician catalogues.

## Sixth branch checkpoint

The authenticated navigation and the complete personal-account workspace now
have a separate, statically checked English/Galician catalogue. Profile and
privacy controls, storage and account metadata, language settings, earned beta
invitations, deleted-library recovery, password/session actions and account
deletion all follow the account preference. Dates in this workspace use the
locale-aware formatter, and visible and assistive labels change together.

To avoid a misleading half-translated product, this slice is route-gated. The
account workspace and its surrounding navigation declare and display the saved
locale; returning to catalogue, map, statistics or layout returns the shell and
document language to English until that workspace receives complete coverage.

## Seventh branch checkpoint

The catalogue browsing surface now has a statically checked English/Galician
catalogue: identity and sharing summary, reading counters, dynamic search,
quick and advanced sorting, all advanced filters and enum labels, book rows,
physical-custody descriptions, accessible action labels, onboarding and empty
states, and pagination. User-authored bibliographic values remain unchanged.

Galician remains intentionally gated off for the catalogue route because the
book details/editor and the reading and loan dialogs it opens are the next
dependent slice. The route must stay consistently English until those dialogs,
their validation/errors and their assistive labels have matching coverage.
