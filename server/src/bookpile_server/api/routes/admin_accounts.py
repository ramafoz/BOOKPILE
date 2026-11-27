from datetime import datetime
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select

from ...models import AccountStorageEntitlement, Library, LibraryStorageAllocation, PlatformRole, SecurityEvent, User
from ...services.auth import utc_value
from ...services.storage_accounting import calculate_account_data_bytes
from ..dependencies import SessionDependency
from .admin_access import AdminSession, require_admin_origin


router = APIRouter(
    prefix="/admin/accounts", tags=["platform accounts"],
    dependencies=[Depends(require_admin_origin)],
)
PAGE_SIZE = 25


class AccountPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    offset: int = Field(default=0, ge=0, le=2_147_483_647)


class AccountDetailRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    account_id: UUID


class AccountSummary(BaseModel):
    account_id: UUID
    username: str
    state: Literal["pending_verification", "active", "suspended", "pending_deletion", "deleted"]
    is_system_admin: bool


class AccountPage(BaseModel):
    accounts: list[AccountSummary]
    next_offset: int | None


class AccountDetail(AccountSummary):
    last_successful_login_at: datetime | None
    storage_used_bytes: int | None
    storage_limit_bytes: int | None


def account_summary_query():
    role = select(PlatformRole.user_id).where(
        PlatformRole.user_id == User.id, PlatformRole.role == "SYSTEM_ADMIN",
    ).exists()
    return select(User.id.label("account_id"), User.username, User.state, role.label("is_system_admin"))


# POST keeps account identifiers out of URLs and lets the browser supply the
# Origin header required by the existing admin session guard.
@router.post("/list", name="admin_list_accounts")
def list_accounts(payload: AccountPageRequest, _access: AdminSession, session: SessionDependency) -> AccountPage:
    rows = session.execute(
        account_summary_query().order_by(User.username).offset(payload.offset).limit(PAGE_SIZE + 1)
    ).mappings().all()
    return AccountPage(
        accounts=[AccountSummary(**row) for row in rows[:PAGE_SIZE]],
        next_offset=payload.offset + PAGE_SIZE if len(rows) > PAGE_SIZE else None,
    )


@router.post("/detail", name="admin_account_detail")
def account_detail(payload: AccountDetailRequest, _access: AdminSession, session: SessionDependency) -> AccountDetail:
    last_login = select(func.max(SecurityEvent.occurred_at)).where(
        SecurityEvent.user_id == User.id, SecurityEvent.event_type == "login_succeeded",
    ).scalar_subquery()
    allocated_bytes = select(func.sum(LibraryStorageAllocation.allocated_bytes)).join(
        Library, Library.id == LibraryStorageAllocation.library_id,
    ).where(LibraryStorageAllocation.user_id == User.id, Library.state == "active").scalar_subquery()
    row = session.execute(
        account_summary_query().add_columns(
            last_login.label("last_login"),
            AccountStorageEntitlement.limit_bytes.label("storage_limit_bytes"),
            allocated_bytes.label("allocated_bytes"),
        ).outerjoin(AccountStorageEntitlement, AccountStorageEntitlement.user_id == User.id)
        .where(User.id == payload.account_id)
    ).mappings().one_or_none()
    if row is None:
        raise HTTPException(404, "Account is unavailable", headers={"Cache-Control": "no-store"})

    storage_used_bytes = None
    if row.storage_limit_bytes is not None:
        # The account's own storage overview uses this same logical accounting
        # plus its allocated shares of active libraries.
        storage_used_bytes = calculate_account_data_bytes(session, payload.account_id) + int(row.allocated_bytes or 0)
    return AccountDetail(
        **row,
        last_successful_login_at=utc_value(row.last_login) if row.last_login is not None else None,
        storage_used_bytes=storage_used_bytes,
    )
