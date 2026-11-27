from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from ..dependencies import SessionDependency
from .admin_access import (
    AdminStepUp,
    limit_attempt,
    require_admin_origin,
    step_up_deadline,
)


router = APIRouter(prefix="/admin/account-invitations", tags=["platform invitations"],
                   dependencies=[Depends(require_admin_origin)])


class RevokeAccountInvitation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    invitation_id: UUID


@router.post("/revoke", status_code=204, dependencies=[Depends(limit_attempt)],
             name="admin_revoke_account_invitation")
def revoke_account_invitation(
    payload: RevokeAccountInvitation, access: AdminStepUp, session: SessionDependency,
) -> None:
    try:
        result = session.scalar(
            text("SELECT platform_actions.revoke_account_invitation(:operator, :invitation, :deadline)"),
            {"operator": access.user_id, "invitation": payload.invitation_id,
             "deadline": step_up_deadline(access)},
        )
        if result == "expired":
            raise HTTPException(403, "Recent WebAuthn reverification required")
        if result == "unavailable":
            raise HTTPException(404, "Account invitation is unavailable")
        if result != "revoked":
            raise HTTPException(503, "Account invitation revocation is unavailable")
        session.commit()
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(503, "Account invitation revocation is unavailable") from exc
