from datetime import datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, joinedload

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
            select(UserSession)
            .options(joinedload(UserSession.user))
            .where(UserSession.token_hash == token_hash)
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

    def revoke_all_user_sessions(self, user_id: UUID, now: datetime) -> None:
        self._session.execute(
            update(UserSession)
            .where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    def commit(self) -> None:
        self._session.commit()
