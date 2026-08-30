from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import AccountInvitation, SecurityEvent


class AccountInvitationRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, invitation: AccountInvitation) -> None:
        self._session.add(invitation)

    def flush(self) -> None:
        self._session.flush()

    def get(self, invitation_id: UUID) -> AccountInvitation | None:
        return self._session.get(AccountInvitation, invitation_id)

    def get_by_token_hash_for_update(
        self, token_hash: str
    ) -> AccountInvitation | None:
        return self._session.scalar(
            select(AccountInvitation)
            .where(AccountInvitation.token_hash == token_hash)
            .with_for_update()
        )

    def add_event(
        self,
        event_type: str,
        *,
        user_id: UUID | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            SecurityEvent(
                user_id=user_id,
                event_type=event_type,
                details=details or {},
            )
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
