from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from hmac import compare_digest
from uuid import UUID

from ..models import UserSession
from ..repositories.auth import AuthRepository
from ..security.passwords import (
    hash_password,
    password_needs_rehash,
    verify_password,
)


INACTIVITY_LIFETIME = timedelta(days=7)
NORMAL_ABSOLUTE_LIFETIME = timedelta(days=30)
REMEMBER_ABSOLUTE_LIFETIME = timedelta(days=90)


def hash_session_secret(secret: str) -> str:
    return sha256(secret.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class LoginResult:
    user_id: UUID
    username: str
    raw_session_token: str
    raw_csrf_token: str
    expires_at: datetime
    absolute_expires_at: datetime


class InvalidCredentialsError(Exception):
    pass


class InvalidSessionError(Exception):
    pass


class InvalidCsrfTokenError(Exception):
    pass


@dataclass(frozen=True)
class AuthContext:
    user_id: UUID
    username: str
    user_session: UserSession


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class AuthService:
    def __init__(self, repository: AuthRepository) -> None:
        self._repository = repository

    def login(
        self,
        *,
        identifier: str,
        password: str,
        remember_me: bool,
        user_agent: str | None,
        ip_address: str | None,
    ) -> LoginResult:
        user = self._repository.find_user_by_identifier(identifier)
        valid_password = verify_password(
            user.password_hash if user is not None else None, password
        )
        allowed = bool(
            user
            and valid_password
            and user.state == "active"
            and user.email_verified_at is not None
        )
        if not allowed:
            self._repository.add_security_event(
                "login_failed",
                user_id=user.id if user is not None else None,
                ip_address=ip_address,
                details={"identifier_kind": "email" if "@" in identifier else "username"},
            )
            self._repository.commit()
            raise InvalidCredentialsError

        assert user is not None
        if password_needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)

        now = datetime.now(UTC)
        absolute_lifetime = (
            REMEMBER_ABSOLUTE_LIFETIME if remember_me else NORMAL_ABSOLUTE_LIFETIME
        )
        raw_session_token, raw_csrf_token = self._new_session(
            user_id=user.id,
            remember_me=remember_me,
            now=now,
            user_agent=user_agent,
            ip_address=ip_address,
            absolute_expires_at=None,
        )
        expires_at = now + INACTIVITY_LIFETIME
        absolute_expires_at = now + absolute_lifetime
        self._repository.add_security_event(
            "login_succeeded", user_id=user.id, ip_address=ip_address
        )
        self._repository.commit()
        return LoginResult(
            user_id=user.id,
            username=user.username,
            raw_session_token=raw_session_token,
            raw_csrf_token=raw_csrf_token,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
        )

    def authenticate(self, raw_session_token: str | None) -> AuthContext:
        if not raw_session_token:
            raise InvalidSessionError
        user_session = self._repository.find_session_by_token_hash(
            hash_session_secret(raw_session_token)
        )
        now = datetime.now(UTC)
        if (
            user_session is None
            or user_session.revoked_at is not None
            or now >= utc_value(user_session.expires_at)
            or now >= utc_value(user_session.absolute_expires_at)
            or user_session.user.state != "active"
            or user_session.user.email_verified_at is None
        ):
            raise InvalidSessionError

        # Avoid one database write per request while still enforcing the
        # seven-day inactivity window accurately enough for interactive use.
        if now - utc_value(user_session.last_seen_at) >= timedelta(minutes=5):
            user_session.last_seen_at = now
            user_session.expires_at = min(
                now + INACTIVITY_LIFETIME,
                utc_value(user_session.absolute_expires_at),
            )
            self._repository.commit()
        return AuthContext(
            user_id=user_session.user.id,
            username=user_session.user.username,
            user_session=user_session,
        )

    def require_csrf(self, context: AuthContext, raw_csrf_token: str | None) -> None:
        if not raw_csrf_token or not compare_digest(
            context.user_session.csrf_token_hash,
            hash_session_secret(raw_csrf_token),
        ):
            raise InvalidCsrfTokenError

    def logout(self, context: AuthContext, *, ip_address: str | None) -> None:
        user_session = context.user_session
        now = datetime.now(UTC)
        self._repository.revoke_session(user_session, now)
        self._repository.add_security_event(
            "logout", user_id=user_session.user_id, ip_address=ip_address
        )
        self._repository.commit()

    def rotate(
        self,
        context: AuthContext,
        *,
        user_agent: str | None,
        ip_address: str | None,
    ) -> LoginResult:
        now = datetime.now(UTC)
        old_session = context.user_session
        absolute_expires_at = utc_value(old_session.absolute_expires_at)
        self._repository.revoke_session(old_session, now)
        raw_session_token, raw_csrf_token = self._new_session(
            user_id=context.user_id,
            remember_me=old_session.remember_me,
            now=now,
            user_agent=user_agent,
            ip_address=ip_address,
            absolute_expires_at=absolute_expires_at,
        )
        self._repository.add_security_event(
            "session_rotated", user_id=context.user_id, ip_address=ip_address
        )
        self._repository.commit()
        return LoginResult(
            user_id=context.user_id,
            username=context.username,
            raw_session_token=raw_session_token,
            raw_csrf_token=raw_csrf_token,
            expires_at=min(now + INACTIVITY_LIFETIME, absolute_expires_at),
            absolute_expires_at=absolute_expires_at,
        )

    def revoke_all(self, context: AuthContext, *, ip_address: str | None) -> None:
        now = datetime.now(UTC)
        self._repository.revoke_all_user_sessions(context.user_id, now)
        self._repository.add_security_event(
            "all_sessions_revoked", user_id=context.user_id, ip_address=ip_address
        )
        self._repository.commit()

    def _new_session(
        self,
        *,
        user_id: UUID,
        remember_me: bool,
        now: datetime,
        user_agent: str | None,
        ip_address: str | None,
        absolute_expires_at: datetime | None,
    ) -> tuple[str, str]:
        if absolute_expires_at is None:
            absolute_lifetime = (
                REMEMBER_ABSOLUTE_LIFETIME
                if remember_me
                else NORMAL_ABSOLUTE_LIFETIME
            )
            absolute_expires_at = now + absolute_lifetime
        raw_session_token = token_urlsafe(32)
        raw_csrf_token = token_urlsafe(32)
        self._repository.add_session(
            UserSession(
                user_id=user_id,
                token_hash=hash_session_secret(raw_session_token),
                csrf_token_hash=hash_session_secret(raw_csrf_token),
                remember_me=remember_me,
                created_at=now,
                last_seen_at=now,
                expires_at=min(now + INACTIVITY_LIFETIME, absolute_expires_at),
                absolute_expires_at=absolute_expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )
        return raw_session_token, raw_csrf_token
