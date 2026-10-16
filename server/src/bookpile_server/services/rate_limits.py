from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import math
from typing import Literal

from sqlalchemy.exc import SQLAlchemyError

from ..repositories.rate_limits import RateLimitRepository

RateLimitMode = Literal["off", "observe", "enforce"]


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    attempts: int
    window: timedelta


@dataclass(frozen=True)
class RateLimitExceededError(Exception):
    retry_after: int


class RateLimitDecisionUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class RateLimitDecision:
    consumed: bool
    exceeded: bool
    retry_after: int | None = None


class RateLimiter:
    def __init__(
        self,
        repository: RateLimitRepository,
        key_secret: str,
        deployment_revision: str = "development",
    ) -> None:
        self._repository = repository
        self._key_secret = key_secret.encode("utf-8")
        self._deployment_revision = deployment_revision

    def enforce(
        self,
        policy: RateLimitPolicy,
        *,
        key: str,
        ip_address: str | None,
        now: datetime | None = None,
    ) -> None:
        self.apply(
            policy,
            key=key,
            mode="enforce",
            ip_address=ip_address,
            record_ip=True,
            now=now,
        )

    def apply(
        self,
        policy: RateLimitPolicy,
        *,
        key: str,
        mode: RateLimitMode,
        ip_address: str | None = None,
        record_ip: bool = False,
        now: datetime | None = None,
    ) -> RateLimitDecision:
        if mode == "off":
            return RateLimitDecision(consumed=False, exceeded=False)
        checked_at = now or datetime.now(UTC)
        key_hash = hmac.new(
            self._key_secret,
            f"{policy.scope}\0{key}".encode("utf-8"),
            sha256,
        ).hexdigest()
        try:
            consumed = self._repository.consume(
                scope=policy.scope,
                key_hash=key_hash,
                now=checked_at,
                reset_before=checked_at - policy.window,
            )
            exceeded = consumed.attempt_count > policy.attempts
            retry_after = (
                self._retry_after(
                    consumed.window_started_at, policy.window, checked_at
                )
                if exceeded
                else None
            )
            if exceeded and consumed.attempt_count == policy.attempts + 1:
                self._record_exceeded(
                    policy=policy,
                    mode=mode,
                    ip_address=ip_address,
                    record_ip=record_ip,
                )
            self._repository.commit()
        except SQLAlchemyError as exc:
            self._repository.rollback()
            raise RateLimitDecisionUnavailableError from exc

        if exceeded:
            assert retry_after is not None
            if mode == "enforce":
                raise RateLimitExceededError(retry_after=retry_after)
            return RateLimitDecision(
                consumed=True, exceeded=True, retry_after=retry_after
            )
        return RateLimitDecision(consumed=True, exceeded=False)

    def _record_exceeded(
        self,
        *,
        policy: RateLimitPolicy,
        mode: RateLimitMode,
        ip_address: str | None,
        record_ip: bool,
    ) -> None:
        if record_ip:
            self._repository.add_blocked_event(
                scope=policy.scope, ip_address=ip_address
            )
            return
        self._repository.add_event(
            event_type=(
                "rate_limit_blocked"
                if mode == "enforce"
                else "rate_limit_observed"
            ),
            scope=policy.scope,
            mode=mode,
            deployment_revision=self._deployment_revision,
            ip_address=None,
        )

    @staticmethod
    def _retry_after(
        window_started_at: datetime,
        window: timedelta,
        checked_at: datetime,
    ) -> int:
        if window_started_at.tzinfo is None:
            window_started_at = window_started_at.replace(tzinfo=UTC)
        return max(
            1,
            math.ceil((window_started_at + window - checked_at).total_seconds()),
        )
