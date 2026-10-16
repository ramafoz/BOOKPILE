from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import OperationLease
from bookpile_server.repositories.operation_leases import OperationLeaseRepository
from bookpile_server.services.operation_leases import (
    LeaseRequest,
    OperationLeaseLostError,
    OperationLeaseManager,
    OperationLeaseUnavailableError,
)


def manager(session: Session) -> OperationLeaseManager:
    return OperationLeaseManager(
        OperationLeaseRepository(session),
        "operation-lease-test-secret",
        ttl=timedelta(minutes=2),
    )


def test_lease_excludes_reacquires_and_fences_stale_owner(session: Session) -> None:
    leases = manager(session)
    started_at = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    first = leases.acquire(
        [LeaseRequest("library_import", "library-1")], now=started_at
    )[0]

    with pytest.raises(OperationLeaseUnavailableError):
        leases.acquire(
            [LeaseRequest("library_import", "library-1")],
            now=started_at + timedelta(minutes=1),
        )

    second = leases.acquire(
        [LeaseRequest("library_import", "library-1")],
        now=started_at + timedelta(minutes=2, seconds=1),
    )[0]
    assert second.lease_id != first.lease_id
    assert second.fencing_token == first.fencing_token + 1
    with pytest.raises(OperationLeaseLostError):
        leases.fence(first, now=started_at + timedelta(minutes=2, seconds=2))
    session.rollback()


def test_release_preserves_monotonic_fencing_token(session: Session) -> None:
    leases = manager(session)
    started_at = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    first = leases.acquire(
        [LeaseRequest("export", "user-1")], now=started_at
    )[0]
    assert leases.release(first, now=started_at + timedelta(seconds=1)) is True

    second = leases.acquire(
        [LeaseRequest("export", "user-1")], now=started_at + timedelta(seconds=2)
    )[0]
    assert second.fencing_token == first.fencing_token + 1
    assert leases.release(first, now=started_at + timedelta(seconds=3)) is False


def test_group_acquisition_is_all_or_nothing(session: Session) -> None:
    leases = manager(session)
    started_at = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    leases.acquire([LeaseRequest("library", "blocked")], now=started_at)

    with pytest.raises(OperationLeaseUnavailableError):
        leases.acquire(
            [
                LeaseRequest("account", "would-have-been-acquired"),
                LeaseRequest("library", "blocked"),
            ],
            now=started_at + timedelta(seconds=1),
        )

    rows = list(session.scalars(select(OperationLease)))
    assert len(rows) == 1


def test_renewal_requires_the_current_unexpired_owner(session: Session) -> None:
    leases = manager(session)
    started_at = datetime(2026, 10, 16, 12, 0, tzinfo=UTC)
    handle = leases.acquire([LeaseRequest("import", "user-1")], now=started_at)[0]
    renewed = leases.renew(handle, now=started_at + timedelta(seconds=30))
    assert renewed.expires_at == started_at + timedelta(minutes=2, seconds=30)

    assert leases.release(renewed, now=started_at + timedelta(seconds=31)) is True
    with pytest.raises(OperationLeaseLostError):
        leases.renew(renewed, now=started_at + timedelta(seconds=32))
