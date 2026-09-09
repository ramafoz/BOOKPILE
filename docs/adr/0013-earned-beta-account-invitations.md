# ADR 0013: Earned beta account invitations

## Decision

During the invitation-only beta, an active account earns one account-invitation
credit for every three distinct UTC dates on which it makes an authenticated
request. A date counts at most once, dates need not be consecutive, and progress
resets to zero whenever a credit is earned. Credits may accumulate.

The private profile shows the three-day progress, available credits and number
of still-usable invitations created by that account. Redeeming a credit creates
the existing cryptographically random, single-use account invitation with a
seven-day expiry. Its raw link is returned and displayed once; BOOKPILE persists
only its hash. Losing the raw link does not restore the credit.

Earned account invitations create new-account eligibility only. They never grant
access to the inviter's libraries. Joining a library still requires a distinct
Owner-issued library invitation after registration and email verification.

## Rationale

Counting dates rather than requests prevents heavy use or automated refreshing
from accelerating invitations. UTC supplies one stable, non-editable boundary
and prevents profile-timezone changes from manufacturing days. Explicit credit
redemption avoids storing recoverable bearer tokens merely so the profile can
display them repeatedly.
