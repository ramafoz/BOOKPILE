from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import case
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import RateLimitBucket, SecurityEvent


@dataclass(frozen=True)
class ConsumedRateLimit:
    attempt_count: int
    window_started_at: datetime


class RateLimitRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def consume(
        self,
        *,
        scope: str,
        key_hash: str,
        now: datetime,
        reset_before: datetime,
    ) -> ConsumedRateLimit:
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "postgresql":
            insert = postgresql_insert(RateLimitBucket)
        elif dialect_name == "sqlite":
            insert = sqlite_insert(RateLimitBucket)
        else:  # pragma: no cover - unsupported deployment safeguard
            raise RuntimeError(f"Unsupported rate-limit database: {dialect_name}")

        statement = insert.values(
            scope=scope,
            key_hash=key_hash,
            window_started_at=now,
            attempt_count=1,
            updated_at=now,
        )
        expired = RateLimitBucket.window_started_at <= reset_before
        statement = statement.on_conflict_do_update(
            index_elements=[RateLimitBucket.scope, RateLimitBucket.key_hash],
            set_={
                "window_started_at": case(
                    (expired, now), else_=RateLimitBucket.window_started_at
                ),
                "attempt_count": case(
                    (expired, 1), else_=RateLimitBucket.attempt_count + 1
                ),
                "updated_at": now,
            },
        ).returning(
            RateLimitBucket.attempt_count,
            RateLimitBucket.window_started_at,
        )
        row = self._session.execute(statement).one()
        return ConsumedRateLimit(
            attempt_count=row.attempt_count,
            window_started_at=row.window_started_at,
        )

    def add_blocked_event(self, *, scope: str, ip_address: str | None) -> None:
        self._session.add(
            SecurityEvent(
                event_type="rate_limit_blocked",
                ip_address=ip_address,
                details={"scope": scope},
            )
        )

    def commit(self) -> None:
        self._session.commit()
