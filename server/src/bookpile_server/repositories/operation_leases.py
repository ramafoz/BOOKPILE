from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import and_, or_, update
from sqlalchemy.dialects.postgresql import insert as postgresql_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from ..models import OperationLease


@dataclass(frozen=True)
class StoredOperationLease:
    scope: str
    key_hash: str
    lease_id: UUID
    fencing_token: int
    expires_at: datetime


class OperationLeaseRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def acquire(
        self,
        *,
        scope: str,
        key_hash: str,
        lease_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> StoredOperationLease | None:
        dialect_name = self._session.get_bind().dialect.name
        if dialect_name == "postgresql":
            insert = postgresql_insert(OperationLease)
        elif dialect_name == "sqlite":
            insert = sqlite_insert(OperationLease)
        else:  # pragma: no cover - unsupported deployment safeguard
            raise RuntimeError(
                f"Unsupported operation-lease database: {dialect_name}"
            )

        statement = insert.values(
            scope=scope,
            key_hash=key_hash,
            lease_id=lease_id,
            fencing_token=1,
            acquired_at=now,
            renewed_at=now,
            expires_at=expires_at,
            released_at=None,
        )
        available = or_(
            OperationLease.released_at.is_not(None),
            OperationLease.expires_at <= now,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[OperationLease.scope, OperationLease.key_hash],
            set_={
                "lease_id": lease_id,
                "fencing_token": OperationLease.fencing_token + 1,
                "acquired_at": now,
                "renewed_at": now,
                "expires_at": expires_at,
                "released_at": None,
            },
            where=available,
        ).returning(
            OperationLease.scope,
            OperationLease.key_hash,
            OperationLease.lease_id,
            OperationLease.fencing_token,
            OperationLease.expires_at,
        )
        row = self._session.execute(statement).one_or_none()
        return self._stored(row) if row is not None else None

    def renew_or_fence(
        self,
        *,
        scope: str,
        key_hash: str,
        lease_id: UUID,
        fencing_token: int,
        now: datetime,
        expires_at: datetime,
    ) -> StoredOperationLease | None:
        statement = (
            update(OperationLease)
            .where(
                and_(
                    OperationLease.scope == scope,
                    OperationLease.key_hash == key_hash,
                    OperationLease.lease_id == lease_id,
                    OperationLease.fencing_token == fencing_token,
                    OperationLease.released_at.is_(None),
                    OperationLease.expires_at > now,
                )
            )
            .values(renewed_at=now, expires_at=expires_at)
            .returning(
                OperationLease.scope,
                OperationLease.key_hash,
                OperationLease.lease_id,
                OperationLease.fencing_token,
                OperationLease.expires_at,
            )
        )
        row = self._session.execute(statement).one_or_none()
        return self._stored(row) if row is not None else None

    def release(
        self,
        *,
        scope: str,
        key_hash: str,
        lease_id: UUID,
        fencing_token: int,
        now: datetime,
    ) -> bool:
        # Keep the row after release so the next owner increments, rather than
        # resets, the fencing token. Expired rows have the same requirement.
        result = self._session.execute(
            update(OperationLease)
            .where(
                OperationLease.scope == scope,
                OperationLease.key_hash == key_hash,
                OperationLease.lease_id == lease_id,
                OperationLease.fencing_token == fencing_token,
                OperationLease.released_at.is_(None),
            )
            .values(released_at=now, expires_at=now)
        )
        return result.rowcount == 1

    def commit(self) -> None:
        self._session.commit()

    def rollback(self) -> None:
        self._session.rollback()

    @staticmethod
    def _stored(row) -> StoredOperationLease:
        expires_at = row.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        return StoredOperationLease(
            scope=row.scope,
            key_hash=row.key_hash,
            lease_id=row.lease_id,
            fencing_token=row.fencing_token,
            expires_at=expires_at,
        )
