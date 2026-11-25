# BOOKPILE

BOOKPILE is a private library manager for cataloguing books, recording reading
history and locating every physical copy in a real room.

This monorepo contains two deliberately separate products:

- **BOOKPILE Local** is the released single-user application for Windows and
  devices on the same private network. It uses SQLite.
- **BOOKPILE Server** is the hosted multi-user edition under active
  development and staging acceptance. It uses PostgreSQL and supports shared
  libraries with Owner and Viewer roles.

They share selected frontend code, visual language and domain concepts, but
not databases, migrations, credentials, runtime state or release lifecycles.

## Start here

### BOOKPILE Local

New Local users should follow the [installation guide](INSTALLATION.md), then
read the [user guide](USER_GUIDE.md). Before changing or moving an existing
catalogue, read [backup and recovery](BACKUP_AND_RECOVERY.md) and
[migration recovery](MIGRATION_RECOVERY.md).

Local developers work in `backend/` and the Local frontend edition. The broad
quality gate is:

```powershell
python -m pytest backend/tests
cd frontend
npm run test:local
npm run lint
npm run build:local
```

### BOOKPILE Server

Server developers should begin with [`server/README.md`](server/README.md).
Hosted deployment, recovery and security procedures live in
[the operations runbook](SERVER_OPERATIONS_AND_SECURITY.md), while
[the production rehearsal runbook](SERVER_PRODUCTION_RUNBOOK.md) defines the
application deployment boundary.

The broad Server quality gate is:

```powershell
python -m pytest server/tests
cd frontend
npm run test:server
npm run lint
npm run build:server
```

These examples are development entry points. Follow the relevant runbook for
migrations, staging, backup, rollback or host changes.

## Repository map

| Path | Purpose |
| --- | --- |
| `backend/` | BOOKPILE Local FastAPI/SQLite backend and tests |
| `server/` | BOOKPILE Server application, migrations, deployment assets and tests |
| `frontend/` | React/TypeScript workspace with explicit Local and Server editions |
| `docs/` | Master plan, active policies, ADRs and specifications |
| `docs/old/` | Preserved historical plans, audits, checklists and snapshots |
| `maintenance/` | Repository maintenance utilities |

Repository and directory-specific working rules are defined in the scoped
`AGENTS.md` files.

## Documentation authority

The [BOOKPILE master work plan](docs/BOOKPILE_MASTER_WORK_PLAN.md) is the only
authority for current status, pending work, blockers and release gates. Do not
infer current status from historical plans or old README snapshots.

Use the [documentation map](docs/README.md) to find active contracts, ADRs,
runbooks and preserved history. Important active references include:

- [Cross-edition data model](CROSS_EDITION_DATA_MODEL.md)
- [Server private object storage](SERVER_PRIVATE_OBJECT_STORAGE.md)
- [Server email outbox](SERVER_EMAIL_OUTBOX.md)
- [Server operational backup and recovery](SERVER_OPERATIONAL_BACKUP.md)
- [Defensive metric catalogue](docs/DEFENSIVE_METRIC_CATALOGUE.md)
- [Log retention and investigation policy](docs/LOG_RETENTION_AND_INVESTIGATION_POLICY.md)

`TODO.md` intentionally contains only a pointer to the master plan.

## Current product direction

BOOKPILE Local remains a supported independent product. Suitable Server
interface improvements may be adapted deliberately for future Local releases
while preserving Local compatibility and its offline/private-network model.

BOOKPILE Server remains private until the master plan's production gates are
explicitly accepted. A successful staging deployment does not authorize
production publication or migration of real user data.

## Licence

See [LICENSE](LICENSE) and [COPYRIGHT](COPYRIGHT).
