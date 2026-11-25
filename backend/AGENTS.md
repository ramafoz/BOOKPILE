# BOOKPILE Local backend guidance

These rules apply to `backend/` and supplement the repository root guidance.

- This is BOOKPILE Local: a single-user SQLite application. Do not import
  Server PostgreSQL models, migrations, authentication, membership or hosted
  configuration into this runtime.
- Preserve compatibility with existing Local catalogues and backups. Schema
  evolution must be explicit, reversible where documented, and covered by
  migration and recovery tests.
- Keep filesystem and cover operations bounded to configured Local paths. Do
  not make tests depend on a user's live catalogue, backups or sibling
  worktree.
- Use synthetic fixtures only. Tests must isolate SQLite databases and object
  directories in temporary locations.
- Run `python -m pytest backend/tests` for backend changes. If a contract shared
  with the frontend changes, also run the Local frontend tests and build.
- Update Local-facing installation, user, backup or recovery documentation
  when behaviour changes; do not copy Server operational procedures into Local
  documentation.
