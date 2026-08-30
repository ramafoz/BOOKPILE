# ADR 0007: Library membership and authorization

- Status: Accepted
- Date: 2026-08-31
- Applies to: BOOKPILE Server

## Context

Authentication proves which account is making a request, but it does not prove
that the account may access a particular library. A library UUID can leak
through logs, browser history, invitations, or ordinary UI links and therefore
must never function as a secret or permission.

BOOKPILE also needs shared libraries without confusing shared ownership of a
physical collection with personal reading activity. During the beta, members
need only two authority levels: equal Owners and read-only Viewers. The
physical map is more sensitive than the catalogue.

## Decision

1. Every protected library operation resolves an authenticated membership.
   Missing and unauthorized library identifiers are normally reported alike,
   so an outsider cannot use the API to enumerate libraries.
2. A library may have several equal `OWNER` members. There is no primary Owner
   and no `EDITOR` role. The final Owner cannot leave or be downgraded.
3. A `VIEWER` is read-only and has either `CATALOG_ONLY` or
   `CATALOG_AND_MAP` scope. Map access always includes catalogue access; a
   map-only scope is invalid.
4. Account-registration invitations and library-sharing invitations are
   separate records, token purposes, and user journeys. Library invitation
   secrets are stored only as hashes, expire, and are single-use.
5. Promotion, downgrade, scope changes, and member removal require current
   password reauthentication. The interface must state the operation's
   concrete consequences before confirmation. Equal co-Ownership includes the
   ability to manage members and eventually to initiate library deletion.
6. Membership and invitation changes produce structured audit events.
7. Reading-perspective selection belongs to the membership. It is read-only
   groundwork in Phase 3; personal reading records are introduced later. If a
   selected Owner ceases to be an Owner, affected selections move to a
   remaining Owner.
8. Phase 1 demonstration libraries are not assigned an invented Owner during
   migration. They remain inaccessible through membership-authorized APIs.

## Consequences

- Knowing or guessing a library UUID is insufficient to read its catalogue.
- Permission changes take effect on subsequent protected operations without
  requiring a global logout.
- The frontend can explain and test catalogue-only versus map-capable viewing
  before the complete physical map is ported.
- Full Viewer-safe response projections still have to be applied to covers,
  physical location, loans, readings, backups, and imports as those domains are
  introduced in later phases.
- Platform administration remains separate from library membership and must
  not silently grant access to private library content.
