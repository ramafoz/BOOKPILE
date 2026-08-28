from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from ..models import SecurityEvent, User, UserSession


class AuthRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_user_by_identifier(self, identifier: str) -> User | None:
        normalized = identifier.strip().lower()
        return self._session.scalar(
            select(User).where(
                or_(User.username == normalized, User.email == normalized)
            )
        )

    def add_session(self, user_session: UserSession) -> None:
        self._session.add(user_session)

    def find_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self._session.scalar(
            select(UserSession).where(UserSession.token_hash == token_hash)
        )

    def add_security_event(
        self,
        event_type: str,
        *,
        user_id: UUID | None,
        ip_address: str | None,
        details: dict[str, object] | None = None,
    ) -> None:
        self._session.add(
            SecurityEvent(
                user_id=user_id,
                event_type=event_type,
                ip_address=ip_address,
                details=details or {},
            )
        )

    def revoke_session(self, user_session: UserSession, now: datetime) -> None:
        user_session.revoked_at = now

    def commit(self) -> None:
        self._session.commit()
