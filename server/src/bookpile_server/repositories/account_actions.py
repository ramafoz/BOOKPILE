from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.orm import Session, selectinload

from ..models import AccountActionToken, SecurityEvent, User, UserSession


class AccountActionRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_user(self, user_id: UUID) -> User | None:
        return self._session.get(User, user_id)

    def find_user_by_email(self, email: str) -> User | None:
        return self._session.scalar(select(User).where(User.email == email))

    def revoke_open_tokens(
        self, *, user_id: UUID, purpose: str, now: datetime
    ) -> None:
        self._session.execute(
            update(AccountActionToken)
            .where(
                AccountActionToken.user_id == user_id,
                AccountActionToken.purpose == purpose,
                AccountActionToken.consumed_at.is_(None),
                AccountActionToken.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def add_token(self, token: AccountActionToken) -> None:
        self._session.add(token)

    def get_token_for_update(
        self, *, token_hash: str, purpose: str
    ) -> AccountActionToken | None:
        return self._session.scalar(
            select(AccountActionToken)
            # Keep the related user out of the locking SELECT. PostgreSQL does
            # not allow FOR UPDATE on the nullable side of joined eager loads.
            .options(selectinload(AccountActionToken.user))
            .where(
                AccountActionToken.token_hash == token_hash,
                AccountActionToken.purpose == purpose,
            )
            .with_for_update()
        )

    def revoke_user_sessions(self, user_id: UUID, now: datetime) -> None:
        self._session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    def add_event(
        self,
        event_type: str,
        *,
        user_id: UUID | None,
        ip_address: str | None = None,
    ) -> None:
        self._session.add(
            SecurityEvent(
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                details={},
            )
        )

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()
