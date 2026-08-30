# ADR 0005: Email verification and password recovery

Status: accepted on 2026-08-30.

## Decision

Email-verification and password-reset links use a shared, purpose-restricted
token table. Random tokens are sent by email and only their hashes are stored.
Verification tokens expire after 24 hours; password-reset tokens after 30
minutes. Issuing a replacement revokes older unused tokens of the same type.

Registration creates a `pending_verification` account and then attempts email
delivery. Database state is committed before SMTP: a mail outage cannot restore
an already consumed account invitation or partially remove the account. A
generic resend endpoint provides recovery.

Password reset is available only to active accounts, changes the Argon2id hash
atomically, consumes the link, and revokes every active session. Request
responses do not reveal whether an email address exists.

Development mail is captured by Mailpit bound to loopback. Production requires
a separately configured authenticated, encrypted email provider.
