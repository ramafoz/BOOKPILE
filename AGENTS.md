# BOOKPILE agent guidance

## Scope and authority

These instructions apply to the entire repository. A more deeply nested
`AGENTS.md` may add directory-specific rules but must not weaken these rules.

- `docs/BOOKPILE_MASTER_WORK_PLAN.md` is the sole authority for current work,
  status, blockers and release gates. Do not create a parallel roadmap.
- Treat ADRs and specifications as normative only for their stated subject.
  Treat `docs/old/` as historical evidence, never as current status.
- Verify claims against the current code and tests. Long-lived README material
  may describe history and must not override the master plan or implementation.

## Product boundary

This monorepo contains two deliberately separate products:

- BOOKPILE Local: `backend/` plus the Local frontend edition; single-user,
  SQLite and Windows/private-LAN oriented.
- BOOKPILE Server: `server/` plus the Server frontend edition; multi-user,
  PostgreSQL and hosted.

They may share frontend source and domain ideas, but never silently share
databases, migrations, credentials, runtime state, release state or security
assumptions. State explicitly which edition a change affects.

## Working method

- Inspect the relevant code, tests and current Git state before proposing or
  changing anything. Preserve unrelated user changes in a dirty worktree.
- Use a focused branch and pull request for each coherent change. Keep changes
  small enough to review and update tests and governing documentation together.
- Use `rg` and `rg --files` for repository searches. Use `apply_patch` for
  hand-written file edits.
- Do not merge, deploy, roll back, restore data, rotate credentials or change
  external services without the user's explicit authorization for that action.
- A green CI run is necessary but not sufficient for security-sensitive,
  migration, recovery or production-readiness changes. Require the documented
  acceptance evidence as well.
- Never discard user work with destructive Git or filesystem commands.

## Safety, privacy and evidence

- Never commit or display secrets, tokens, passwords, cookies, private object
  keys, raw personal data or environment-file contents.
- Prefer aggregate, bounded and redacted evidence. Do not expose client IPs in
  ordinary output. The audited D3-L procedure is the only approved path for an
  explicitly authorized, single-event attribution.
- Authorization must derive from authenticated membership and role checks, not
  possession of a path identifier. Preserve tenant scoping and fail-closed
  behaviour.
- Treat backup, restore, migration, deletion, firewall and SYSTEM_ADMIN work as
  high risk. Follow the relevant runbook exactly and preserve recovery paths.
- Generated evidence and runtime artefacts belong outside version control.

## Validation

Run the smallest relevant checks while iterating, then the complete affected
quality gate before handoff. The repository CI definition is the canonical
list of broad gates. At minimum, consider:

- Local backend: `python -m pytest backend/tests`
- Server backend: `python -m pytest server/tests`
- Frontend: from `frontend/`, `npm run test:local`, `npm run test:server`,
  `npm run lint`, and `npm run build:all`
- Deployment scripts: `bash server/deploy/tests/test-deploy-staging.sh`

Do not claim a command passed unless it was actually run. Report skipped or
unavailable checks and the reason.

## User-facing operational commands

When guiding the operator through PowerShell, SSH or the IONOS console, provide
one single-line command at a time and wait for its result. Do not use multiline
continuations or mix explanatory text into a copyable command. Explain expected
state changes before commands that deploy, disable protection or recover data.
Use the runbook's exact typed confirmations such as `DEPLOY` and `ROLLBACK`.

## Documentation

- Keep the root README a concise landing page, not a second work plan.
- Put Local user/release guidance in `docs/local/`, Server operational
  procedures in `docs/server/`, architecture decisions in `docs/adr/`, and
  behavioural contracts in `docs/specifications/`.
- Record task status only in the master plan. Archive superseded narrative in
  `docs/old/` without presenting it as current guidance.
- Keep links relative and update affected documentation in the same pull
  request as the behaviour it describes.
