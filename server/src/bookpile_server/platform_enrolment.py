"""Host-side platform role transitions and their immutable audit records."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection, Engine
from sqlalchemy.orm import Session

from .admin_audit import AuditAppend, append_in_transaction
from .models import PlatformAdminAccess, PlatformRole, User
from .services.auth import hash_session_secret, utc_value


EnrolmentAction = Literal["enrol", "revoke", "prepare-passkey"]
ENROLMENT_REASONS = ("bootstrap", "operator-change", "access-retirement", "incident-response")


@dataclass(frozen=True)
class EnrolmentRequest:
    action: EnrolmentAction
    target: UUID
    operator: str
    reason: str
    correlation_id: UUID


def _target_is_eligible(
    connection: Connection, request: EnrolmentRequest, operator_email: str, *, lock: bool
) -> bool:
    query = select(User.state, User.email_verified_at, User.email).where(
        User.id == request.target
    )
    if lock:
        query = query.with_for_update()
    account = connection.execute(query).one_or_none()
    if account is None or account.email.casefold() == operator_email.casefold():
        return False
    return request.action == "revoke" or (
        account.state == "active" and account.email_verified_at is not None
    )


def target_is_eligible(engine: Engine, request: EnrolmentRequest, operator_email: str) -> bool:
    with engine.connect() as connection:
        return _target_is_eligible(connection, request, operator_email, lock=False)


def record_enrolment(
    engine: Engine,
    request: EnrolmentRequest,
    operator_email: str,
    *,
    confirmed: bool,
) -> bool:
    """Commit a role change and its audit row together, including on revocation."""
    if request.action not in {"enrol", "revoke"}:
        raise ValueError("Unsupported platform role transition")
    with engine.begin() as connection:
        changed = confirmed and _target_is_eligible(
            connection, request, operator_email, lock=True
        )
        if changed:
            assignment = (PlatformRole.user_id == request.target) & (
                PlatformRole.role == "SYSTEM_ADMIN"
            )
            if request.action == "enrol":
                changed = connection.scalar(select(PlatformRole.role).where(assignment)) is None
                if changed:
                    connection.execute(
                        insert(PlatformRole).values(user_id=request.target, role="SYSTEM_ADMIN")
                    )
            else:
                result = connection.execute(delete(PlatformRole).where(assignment))
                changed = result.rowcount == 1

        append_in_transaction(
            connection,
            AuditAppend(
                operator_id=request.operator,
                action=f"platform_admin.{request.action}",
                target_id=str(request.target),
                reason=request.reason,
                correlation_id=str(request.correlation_id),
                result="succeeded" if changed else "failed",
            ),
        )
    return changed


def prepare_first_passkey(
    engine: Engine,
    request: EnrolmentRequest,
    operator_email: str,
    code: str,
    deliver_code: Callable[[], bool],
) -> bool:
    """Issue an operator confirmation and audit the host action atomically."""
    if request.action != "prepare-passkey":
        raise ValueError("Unsupported passkey preparation action")
    with Session(engine) as session, session.begin():
        connection = session.connection()
        now = datetime.now(UTC)
        eligible = _target_is_eligible(connection, request, operator_email, lock=True)
        role = session.get(PlatformRole, (request.target, "SYSTEM_ADMIN")) if eligible else None
        access = session.get(PlatformAdminAccess, request.target, with_for_update=True) if role else None
        changed = bool(
            role and (access is None or (
                access.credential_id is None and utc_value(access.bootstrap_expires_at) <= now
            )) and deliver_code()
        )
        if changed:
            if access is None:
                access = PlatformAdminAccess(user_id=request.target)
                session.add(access)
            access.bootstrap_hash = hash_session_secret(code)
            access.bootstrap_expires_at = now + timedelta(minutes=10)
            access.challenge = access.challenge_session_id = access.challenge_expires_at = None
            session.flush()
        append_in_transaction(connection, AuditAppend(
            operator_id=request.operator, action="platform_admin.prepare_passkey",
            target_id=str(request.target), reason=request.reason,
            correlation_id=str(request.correlation_id),
            result="succeeded" if changed else "failed",
        ))
    return changed
