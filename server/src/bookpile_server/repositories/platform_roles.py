from uuid import UUID

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from ..models import PlatformRole


def has_system_admin_role(session: Session, user_id: UUID) -> bool:
    """Look up the platform grant. Admin authentication is a separate check."""
    assignment = exists().where(
        PlatformRole.user_id == user_id,
        PlatformRole.role == "SYSTEM_ADMIN",
    )
    return bool(session.scalar(select(assignment)))
