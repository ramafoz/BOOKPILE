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
- For every invitation that is actually *sent*, the inviter must choose the
  recipient language explicitly. Store that choice on the invitation/outbox
  event so retries use the same language. It may differ from the inviter's
  account preference and must never change it. The invited person can choose
  a different interface/account preference during registration or acceptance.
  This applies to both account and library invitations when email delivery is
  implemented. Today those flows generate a link/token; they do not send an
  invitation email, so no email-language selector should pretend otherwise.
- Account-action emails (verification, password reset, deletion recovery) use
  the recipient account preference captured at queue time, not an inviter's
  choice. Unknown-account responses remain generic in every language.

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
workspace translations. No email templates or invitation delivery changed.
