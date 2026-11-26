"""Host-side platform role transitions and their immutable audit records."""

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from sqlalchemy import delete, insert, select
from sqlalchemy.engine import Connection, Engine

from .admin_audit import AuditAppend, append_in_transaction
from .models import PlatformRole, User


EnrolmentAction = Literal["enrol", "revoke"]
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
