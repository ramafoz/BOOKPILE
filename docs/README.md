# BOOKPILE documentation map

Documentation has one status authority:

- [BOOKPILE master work plan](BOOKPILE_MASTER_WORK_PLAN.md) — the only source
  for delivery status, pending work, release blockers and go/no-go gates.

Other documentation has a narrower role:

- [`LOG_RETENTION_AND_INVESTIGATION_POLICY.md`](LOG_RETENTION_AND_INVESTIGATION_POLICY.md)
  is the binding hosted-log field, expiry and access contract. Completion and
  staging evidence remain exclusively in the master plan.
- `docs/adr/` records accepted architectural decisions. An ADR may define how a
  task must be implemented, but task status lives only in the master plan.
- `docs/specifications/` contains active normative product/domain contracts.
  Specifications define behaviour but do not maintain independent task status.
- Root operational documents are live specifications and runbooks for
  deployment, backup, security and recovery. They must not maintain independent
  pending-work lists.
- `docs/old/` contains historical plans and snapshots. Their checkboxes,
  progress percentages, providers, quotas and dates are not current status.

When implementation changes a decision, update the relevant ADR or runbook and
the master plan in the same pull request. Never create another roadmap.
