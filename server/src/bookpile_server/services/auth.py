from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
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
    expires_at: datetime
    absolute_expires_at: datetime


class InvalidCredentialsError(Exception):
    pass


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
        raw_session_token = token_urlsafe(32)
        raw_csrf_token = token_urlsafe(32)
        expires_at = now + INACTIVITY_LIFETIME
        absolute_expires_at = now + absolute_lifetime
        self._repository.add_session(
            UserSession(
                user_id=user.id,
                token_hash=hash_session_secret(raw_session_token),
                csrf_token_hash=hash_session_secret(raw_csrf_token),
                remember_me=remember_me,
                created_at=now,
                last_seen_at=now,
                expires_at=expires_at,
                absolute_expires_at=absolute_expires_at,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )
        self._repository.add_security_event(
            "login_succeeded", user_id=user.id, ip_address=ip_address
        )
        self._repository.commit()
        return LoginResult(
            user_id=user.id,
            username=user.username,
            raw_session_token=raw_session_token,
            expires_at=expires_at,
            absolute_expires_at=absolute_expires_at,
        )

    def logout(self, raw_session_token: str | None, *, ip_address: str | None) -> None:
        if not raw_session_token:
            return
        user_session = self._repository.find_session_by_token_hash(
            hash_session_secret(raw_session_token)
        )
        if user_session is None or user_session.revoked_at is not None:
            return
        now = datetime.now(UTC)
        self._repository.revoke_session(user_session, now)
        self._repository.add_security_event(
            "logout", user_id=user_session.user_id, ip_address=ip_address
        )
        self._repository.commit()
