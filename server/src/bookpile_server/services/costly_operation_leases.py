from dataclasses import dataclass
from datetime import timedelta
from typing import Callable
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ..config import Settings
from ..repositories.rate_limits import RateLimitRepository
from .operation_leases import (
    LeaseRequest,
    OperationLeaseManager,
    OperationLeaseUnavailableError,
    RenewableOperationLeaseGuard,
)


@dataclass(frozen=True)
class CostlyOperationLeaseUnavailableError(Exception):
    scope: str


class CostlyOperationLeaseDecisionUnavailableError(Exception):
    pass


class CostlyOperationLeaseService:
    def __init__(
        self,
        manager: OperationLeaseManager,
        event_repository: RateLimitRepository,
        session_factory: Callable[[], Session],
        settings: Settings,
    ) -> None:
        self._manager = manager
        self._events = event_repository
        self._session_factory = session_factory
        self._settings = settings

    def acquire_export(
        self, *, user_id: UUID, library_id: UUID
    ) -> RenewableOperationLeaseGuard | None:
        mode = self._settings.defensive_limit_mode
        if mode == "off":
            return None
        try:
            handles = self._manager.acquire(
                (
                    LeaseRequest("portable_export_user", str(user_id)),
                    LeaseRequest("portable_export_library", str(library_id)),
                )
            )
        except OperationLeaseUnavailableError as exc:
            try:
                self._events.add_event(
                    event_type=(
                        "operation_lease_blocked"
                        if mode == "enforce"
                        else "operation_lease_observed"
                    ),
                    scope=exc.scope,
                    mode=mode,
                    deployment_revision=self._settings.deployment_revision,
                    ip_address=None,
                )
                self._events.commit()
            except SQLAlchemyError as database_error:
                self._events.rollback()
                raise CostlyOperationLeaseDecisionUnavailableError from database_error
            if mode == "enforce":
                raise CostlyOperationLeaseUnavailableError(exc.scope) from exc
            return None
        except SQLAlchemyError as exc:
            raise CostlyOperationLeaseDecisionUnavailableError from exc

        return RenewableOperationLeaseGuard(
            handles,
            self._session_factory,
            self._settings.rate_limit_key_secret,
            ttl=timedelta(seconds=self._settings.operation_lease_ttl_seconds),
            heartbeat=timedelta(
                seconds=self._settings.operation_lease_heartbeat_seconds
            ),
        )
