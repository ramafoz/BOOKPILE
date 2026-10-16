from datetime import timedelta

import pytest
from sqlalchemy import func, select, update
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
    first = leases.acquire([LeaseRequest("library_import", "library-1")])[0]

    with pytest.raises(OperationLeaseUnavailableError):
        leases.acquire([LeaseRequest("library_import", "library-1")])

    session.execute(
        update(OperationLease).values(
            expires_at=func.datetime("now", "-1 second")
        )
    )
    session.commit()

    second = leases.acquire([LeaseRequest("library_import", "library-1")])[0]
    assert second.lease_id != first.lease_id
    assert second.fencing_token == first.fencing_token + 1
    with pytest.raises(OperationLeaseLostError):
        leases.fence(first)
    session.rollback()


def test_release_preserves_monotonic_fencing_token(session: Session) -> None:
    leases = manager(session)
    first = leases.acquire([LeaseRequest("export", "user-1")])[0]
    assert leases.release(first) is True

    second = leases.acquire([LeaseRequest("export", "user-1")])[0]
    assert second.fencing_token == first.fencing_token + 1
    assert leases.release(first) is False


def test_group_acquisition_is_all_or_nothing(session: Session) -> None:
    leases = manager(session)
    leases.acquire([LeaseRequest("library", "blocked")])

    with pytest.raises(OperationLeaseUnavailableError):
        leases.acquire(
            [
                LeaseRequest("account", "would-have-been-acquired"),
                LeaseRequest("library", "blocked"),
            ],
        )

    rows = list(session.scalars(select(OperationLease)))
    assert len(rows) == 1


def test_renewal_requires_the_current_unexpired_owner(session: Session) -> None:
    leases = manager(session)
    handle = leases.acquire([LeaseRequest("import", "user-1")])[0]
    renewed = leases.renew(handle)
    assert renewed.expires_at >= handle.expires_at

    assert leases.release(renewed) is True
    with pytest.raises(OperationLeaseLostError):
        leases.renew(renewed)
