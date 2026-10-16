from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
import hmac
from uuid import UUID, uuid4

from ..repositories.operation_leases import (
    OperationLeaseRepository,
    StoredOperationLease,
)


@dataclass(frozen=True)
class LeaseRequest:
    scope: str
    key: str


@dataclass(frozen=True)
class OperationLeaseHandle:
    scope: str
    key_hash: str
    lease_id: UUID
    fencing_token: int
    expires_at: datetime


@dataclass(frozen=True)
class OperationLeaseUnavailableError(Exception):
    scope: str


@dataclass(frozen=True)
class OperationLeaseLostError(Exception):
    scope: str


class OperationLeaseManager:
    """Coordinate costly work across every API worker through the database.

    ``fence`` intentionally leaves the transaction open. The caller must perform
    the protected database writes and commit them using the same Session, making
    the ownership check and the domain commit one atomic transaction.
    """

    def __init__(
        self,
        repository: OperationLeaseRepository,
        key_secret: str,
        *,
        ttl: timedelta = timedelta(minutes=2),
    ) -> None:
        if ttl <= timedelta(0):
            raise ValueError("Operation-lease TTL must be positive")
        self._repository = repository
        self._key_secret = key_secret.encode("utf-8")
        self._ttl = ttl

    def acquire(
        self,
        requests: list[LeaseRequest] | tuple[LeaseRequest, ...],
        *,
        now: datetime | None = None,
    ) -> tuple[OperationLeaseHandle, ...]:
        checked_at = now or datetime.now(UTC)
        prepared = sorted(
            (self._prepare(request) for request in requests),
            key=lambda item: (item[0], item[1]),
        )
        if not prepared:
            raise ValueError("At least one operation lease is required")
        if len({(scope, key_hash) for scope, key_hash in prepared}) != len(prepared):
            raise ValueError("Duplicate operation-lease request")

        acquired: list[OperationLeaseHandle] = []
        try:
            for scope, key_hash in prepared:
                stored = self._repository.acquire(
                    scope=scope,
                    key_hash=key_hash,
                    lease_id=uuid4(),
                    now=checked_at,
                    expires_at=checked_at + self._ttl,
                )
                if stored is None:
                    raise OperationLeaseUnavailableError(scope=scope)
                acquired.append(self._handle(stored))
            self._repository.commit()
        except Exception:
            self._repository.rollback()
            raise
        return tuple(acquired)

    def renew(
        self,
        handle: OperationLeaseHandle,
        *,
        now: datetime | None = None,
    ) -> OperationLeaseHandle:
        checked_at = now or datetime.now(UTC)
        stored = self._renew_or_fence(handle, checked_at)
        if stored is None:
            self._repository.rollback()
            raise OperationLeaseLostError(scope=handle.scope)
        self._repository.commit()
        return self._handle(stored)

    def fence(
        self,
        handle: OperationLeaseHandle,
        *,
        now: datetime | None = None,
    ) -> OperationLeaseHandle:
        """Lock and validate a lease inside the caller's domain transaction."""

        checked_at = now or datetime.now(UTC)
        stored = self._renew_or_fence(handle, checked_at)
        if stored is None:
            raise OperationLeaseLostError(scope=handle.scope)
        return self._handle(stored)

    def release(
        self,
        handle: OperationLeaseHandle,
        *,
        now: datetime | None = None,
    ) -> bool:
        released = self._repository.release(
            scope=handle.scope,
            key_hash=handle.key_hash,
            lease_id=handle.lease_id,
            fencing_token=handle.fencing_token,
            now=now or datetime.now(UTC),
        )
        self._repository.commit()
        return released

    def _prepare(self, request: LeaseRequest) -> tuple[str, str]:
        scope = request.scope.strip()
        key = request.key.strip()
        if not scope or len(scope) > 64:
            raise ValueError("Operation-lease scope must contain 1 to 64 characters")
        if not key:
            raise ValueError("Operation-lease key must not be empty")
        key_hash = hmac.new(
            self._key_secret,
            f"operation_lease\0{scope}\0{key}".encode("utf-8"),
            sha256,
        ).hexdigest()
        return scope, key_hash

    def _renew_or_fence(
        self, handle: OperationLeaseHandle, checked_at: datetime
    ) -> StoredOperationLease | None:
        return self._repository.renew_or_fence(
            scope=handle.scope,
            key_hash=handle.key_hash,
            lease_id=handle.lease_id,
            fencing_token=handle.fencing_token,
            now=checked_at,
            expires_at=checked_at + self._ttl,
        )

    @staticmethod
    def _handle(stored: StoredOperationLease) -> OperationLeaseHandle:
        return OperationLeaseHandle(
            scope=stored.scope,
            key_hash=stored.key_hash,
            lease_id=stored.lease_id,
            fencing_token=stored.fencing_token,
            expires_at=stored.expires_at,
        )
