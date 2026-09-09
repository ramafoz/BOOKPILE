from datetime import UTC, date, datetime
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.orm import Session, joinedload

from ..models import BetaInvitationProgress, SecurityEvent, User, UserSession


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

    def find_user(self, user_id: UUID) -> User | None:
        return self._session.get(User, user_id)

    def add_session(self, user_session: UserSession) -> None:
        self._session.add(user_session)

    def find_session_by_token_hash(self, token_hash: str) -> UserSession | None:
        return self._session.scalar(
            select(UserSession)
            .options(joinedload(UserSession.user))
            .where(UserSession.token_hash == token_hash)
        )

    def record_beta_activity_day(self, user_id: UUID, active_on: date) -> bool:
        progress = self._session.scalar(
            select(BetaInvitationProgress)
            .where(BetaInvitationProgress.user_id == user_id)
            .with_for_update()
        )
        if progress is None:
            progress = BetaInvitationProgress(
                user_id=user_id, active_day_count=1, last_active_on=active_on
            )
            self._session.add(progress)
            return True
        if progress.last_active_on == active_on:
            return False
        next_count = progress.active_day_count + 1
        if next_count >= 3:
            progress.active_day_count = 0
            progress.available_credits += 1
        else:
            progress.active_day_count = next_count
        progress.last_active_on = active_on
        progress.updated_at = datetime.now(UTC)
        return True

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

    def revoke_other_user_sessions(
        self, user_id: UUID, current_session_id: UUID, now: datetime
    ) -> None:
        self._session.execute(
            update(UserSession)
            .where(
                UserSession.user_id == user_id,
                UserSession.id != current_session_id,
                UserSession.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    def commit(self) -> None:
        self._session.commit()
