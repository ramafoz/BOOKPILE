# BOOKPILE documentation guidance

These rules apply to `docs/` and supplement the repository root guidance.

- `BOOKPILE_MASTER_WORK_PLAN.md` is the only delivery-status authority. Add or
  close work there; do not add competing checklists elsewhere.
- ADRs record durable architectural decisions and their consequences.
  Specifications describe active behaviour. Neither should carry an
  independent project-status narrative.
- `old/` is archival. Preserve useful provenance, label it clearly as
  historical and do not repair old status claims as though they were current.
- Keep `README.md` as the documentation map and update it when documents are
  added, moved, archived or change authority.
- Separate observed evidence from inference. Include dates and revisions for
  acceptance evidence, but never secrets, client addresses, private object
  identifiers or personal data.
- Prefer relative links and check every changed link. When moving a document,
  update inbound references in the same pull request.
- Documentation-only changes must still be internally consistent with current
  code, runbooks and the master plan.
