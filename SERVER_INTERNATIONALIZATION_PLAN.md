# BOOKPILE Server internationalization

The private beta targets English (`en`), Galician (`gl`), Portuguese (`pt`),
Spanish (`es`), Italian (`it`), Catalan (`ca`), Basque (`eu`), French (`fr`), and
Simplified Chinese (`zh-Hans`). Language of the interface is independent of a
book's bibliographic language. English is the source catalogue and fallback.

## Delivery slices

- [ ] Establish typed message catalogues, locale resolution, browser preference,
  document language and regional formatting. Make only complete locales
  selectable; do not present untranslated pages as translated.
- [ ] Translate the entire unauthenticated account journey: invitation signup,
  verification, sign-in, reset and deletion recovery. Preserve generic responses
  that avoid account enumeration. Localize safe API error codes, never raw server
  exception text.
- [ ] Translate the authenticated shell, account and library controls, catalogue,
  map, statistics, readings, loans, imports/exports, dialogs and notices. Audit
  screen-reader labels, empty states and mobile widths for longer strings.
- [ ] Persist the account preference server-side for cross-device use. Before
  sign-in, use a best-effort browser preference; define precedence and a
  privacy-safe API migration. Browser storage must not contain tokens.
- [ ] Localize every transactional email in text and HTML, using the account
  preference captured when the message is queued. Keep subject, action and
  expiry copy consistent, and preserve SMTP/DKIM behavior and privacy rules.
- [ ] Add the remaining seven locales in reviewed batches; verify plural rules,
  dates, numbers and relative time with `Intl`, plus typography and CJK font
  fallback. User-generated names and book metadata are never machine-translated.
- [ ] Run end-to-end language switching, reload, fresh browser, cross-device,
  auth links, email, accessibility and mobile tests before beta acceptance.

Do not expose a locale in the selector until its current route is covered. A
feature branch may contain a partial migration; staging promotion waits for a
coherent full-user journey.

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
