# BOOKPILE frontend guidance

These rules apply to `frontend/` and supplement the repository root guidance.

- One workspace builds two explicit editions. Keep Local and Server entry
  points, API assumptions, tests and output directories separate.
- A shared component change must be checked in both editions. Do not expose a
  Server-only control in Local or assume Server authentication in Local.
- Preserve authorization in the API; hiding or disabling a frontend control is
  not a security boundary.
- Keep responsive desktop/mobile behaviour and keyboard/touch interaction in
  scope. Avoid regressions in map pan/zoom, forms and destructive confirmations.
- User-visible Server strings belong in the locale system. Update every
  supported locale or follow the repository's explicit fallback contract;
  never silently hard-code English into a translated view.
- Preserve privacy: do not place secrets, raw identifiers or sensitive error
  details in URLs, analytics, browser logs or translated messages.

From `frontend/`, run:

- `npm run test:local`
- `npm run test:server`
- `npm run lint`
- `npm run build:all`

Use `npm ci` when a clean dependency installation is needed. Commit
`package-lock.json` whenever `package.json` dependency resolution changes.
