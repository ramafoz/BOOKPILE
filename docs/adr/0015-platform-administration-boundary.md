# ADR 0015: Platform administration is not library ownership

## Decision

BOOKPILE platform operations and future `SYSTEM_ADMIN` capabilities are a
separate authorization domain from `OWNER` and `VIEWER`. A platform operator
receives no implicit membership and no application route may treat system
administration as permission to read a private library.

The original decision deferred a browser administration panel during the
private beta. That timing decision is superseded by ADR 0017: a restricted web
`SYSTEM_ADMIN` console is now a production blocker. The authorization boundary
in this ADR remains unchanged. Host-side maintenance may process expiry,
aggregate health and integrity but must not print private content, object keys,
request queries, tokens or email bodies.

## Consequences

- Support cannot casually impersonate members or inspect their libraries.
- Infrastructure recovery can touch encrypted/storage layers only for integrity
  restoration under incident procedure.
- Account abuse tooling is limited by ADR 0017. Public/social moderation remains
  separately designed future work.
