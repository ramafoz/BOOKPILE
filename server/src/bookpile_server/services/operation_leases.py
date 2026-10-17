from dataclasses import dataclass
from datetime import datetime, timedelta
from hashlib import sha256
import hmac
from threading import Event, Lock, Thread
from types import TracebackType
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy.orm import Session

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


class RenewableOperationLeaseGuard:
    """Keep a set of leases alive using short, independent DB sessions."""

    def __init__(
        self,
        handles: tuple[OperationLeaseHandle, ...],
        session_factory: Callable[[], Session],
        key_secret: str,
        *,
        ttl: timedelta,
        heartbeat: timedelta,
    ) -> None:
        if not handles:
            raise ValueError("At least one acquired lease is required")
        if heartbeat <= timedelta(0) or heartbeat * 2 > ttl:
            raise ValueError("Lease heartbeat must fit safely inside its TTL")
        self._handles = handles
        self._session_factory = session_factory
        self._key_secret = key_secret
        self._ttl = ttl
        self._heartbeat_seconds = heartbeat.total_seconds()
        self._stop = Event()
        self._lock = Lock()
        self._failure: Exception | None = None
        self._failure_listeners: set[Callable[[], None]] = set()
        self._closed = False
        self._thread = Thread(
            target=self._heartbeat_loop,
            name="bookpile-operation-lease-heartbeat",
            daemon=True,
        )
        self._thread.start()

    def ensure_owned(self) -> None:
        with self._lock:
            failure = self._failure
        if failure is not None:
            raise failure

    def fence(self, session: Session) -> None:
        """Atomically validate every lease inside a domain-write transaction.

        The lease rows remain locked until the caller commits or rolls back the
        supplied session. This closes the gap between an ownership check and
        the protected domain commit.
        """

        self.ensure_owned()
        manager = OperationLeaseManager(
            OperationLeaseRepository(session),
            self._key_secret,
            ttl=self._ttl,
        )
        with self._lock:
            handles = self._handles
        fenced = tuple(manager.fence(handle) for handle in handles)
        with self._lock:
            self._handles = fenced

    def add_failure_listener(self, listener: Callable[[], None]) -> None:
        notify_now = False
        with self._lock:
            if self._failure is None:
                self._failure_listeners.add(listener)
            else:
                notify_now = True
        if notify_now:
            listener()

    def remove_failure_listener(self, listener: Callable[[], None]) -> None:
        with self._lock:
            self._failure_listeners.discard(listener)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
        self._stop.set()
        self._thread.join(timeout=self._heartbeat_seconds + 1)
        with self._lock:
            handles = self._handles
        # Release is best effort: a failed release is recovered by lease expiry.
        try:
            with self._session_factory() as session:
                manager = OperationLeaseManager(
                    OperationLeaseRepository(session),
                    self._key_secret,
                    ttl=self._ttl,
                )
                for handle in handles:
                    manager.release(handle)
        except Exception:
            pass

    def __enter__(self) -> "RenewableOperationLeaseGuard":
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        self.close()

    def _heartbeat_loop(self) -> None:
        while not self._stop.wait(self._heartbeat_seconds):
            try:
                renewed: list[OperationLeaseHandle] = []
                with self._lock:
                    handles = self._handles
                with self._session_factory() as session:
                    manager = OperationLeaseManager(
                        OperationLeaseRepository(session),
                        self._key_secret,
                        ttl=self._ttl,
                    )
                    for handle in handles:
                        renewed.append(manager.renew(handle))
                with self._lock:
                    self._handles = tuple(renewed)
            except Exception as exc:
                with self._lock:
                    self._failure = exc
                    listeners = tuple(self._failure_listeners)
                for listener in listeners:
                    try:
                        listener()
                    except Exception:
                        pass
                self._stop.set()
                return


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
    ) -> tuple[OperationLeaseHandle, ...]:
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
                    ttl=self._ttl,
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
    ) -> OperationLeaseHandle:
        stored = self._renew_or_fence(handle)
        if stored is None:
            self._repository.rollback()
            raise OperationLeaseLostError(scope=handle.scope)
        self._repository.commit()
        return self._handle(stored)

    def fence(
        self,
        handle: OperationLeaseHandle,
    ) -> OperationLeaseHandle:
        """Lock and validate a lease inside the caller's domain transaction."""

        stored = self._renew_or_fence(handle)
        if stored is None:
            raise OperationLeaseLostError(scope=handle.scope)
        return self._handle(stored)

    def release(
        self,
        handle: OperationLeaseHandle,
    ) -> bool:
        released = self._repository.release(
            scope=handle.scope,
            key_hash=handle.key_hash,
            lease_id=handle.lease_id,
            fencing_token=handle.fencing_token,
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
        self, handle: OperationLeaseHandle
    ) -> StoredOperationLease | None:
        return self._repository.renew_or_fence(
            scope=handle.scope,
            key_hash=handle.key_hash,
            lease_id=handle.lease_id,
            fencing_token=handle.fencing_token,
            ttl=self._ttl,
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
