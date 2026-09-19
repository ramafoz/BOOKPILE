# ADR 0015: Platform administration is not library ownership

## Decision

BOOKPILE platform operations and future `SYSTEM_ADMIN` capabilities are a
separate authorization domain from `OWNER` and `VIEWER`. A platform operator
receives no implicit membership and no application route may treat system
administration as permission to read a private library.

The private beta exposes no browser administration panel. Host-side maintenance
may process expiry, aggregate health and integrity but must not print identities,
library names, object keys, request queries, tokens or content. A later admin
domain needs independent authentication, immutable operator audit and explicit
per-action policy before UI work begins.

## Consequences

- Support cannot casually impersonate members or inspect their libraries.
- Infrastructure recovery can touch encrypted/storage layers only for integrity
  restoration under incident procedure.
- Account abuse tooling and public/social moderation remain separately designed
  future work.
