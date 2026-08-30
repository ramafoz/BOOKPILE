from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
import math

from ..repositories.rate_limits import RateLimitRepository


@dataclass(frozen=True)
class RateLimitPolicy:
    scope: str
    attempts: int
    window: timedelta


@dataclass(frozen=True)
class RateLimitExceededError(Exception):
    retry_after: int


class RateLimiter:
    def __init__(self, repository: RateLimitRepository, key_secret: str) -> None:
        self._repository = repository
        self._key_secret = key_secret.encode("utf-8")

    def enforce(
        self,
        policy: RateLimitPolicy,
        *,
        key: str,
        ip_address: str | None,
        now: datetime | None = None,
    ) -> None:
        checked_at = now or datetime.now(UTC)
        key_hash = hmac.new(
            self._key_secret,
            f"{policy.scope}\0{key}".encode("utf-8"),
            sha256,
        ).hexdigest()
        consumed = self._repository.consume(
            scope=policy.scope,
            key_hash=key_hash,
            now=checked_at,
            reset_before=checked_at - policy.window,
        )
        if consumed.attempt_count > policy.attempts:
            if consumed.attempt_count == policy.attempts + 1:
                self._repository.add_blocked_event(
                    scope=policy.scope, ip_address=ip_address
                )
            self._repository.commit()
            window_started_at = consumed.window_started_at
            if window_started_at.tzinfo is None:
                window_started_at = window_started_at.replace(tzinfo=UTC)
            retry_after = max(
                1,
                math.ceil(
                    (
                        window_started_at + policy.window - checked_at
                    ).total_seconds()
                ),
            )
            raise RateLimitExceededError(retry_after=retry_after)
        self._repository.commit()
