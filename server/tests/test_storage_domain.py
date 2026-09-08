from uuid import UUID

import pytest

from bookpile_server.services.storage_domain import (
    ACCOUNT_QUOTA_BYTES,
    AccountCapacity,
    InsufficientSharedCapacity,
    LibraryDemand,
    StorageRuleViolation,
    allocate_storage,
    logical_collection_bytes,
    logical_record_bytes,
)


def uid(value: int) -> UUID:
    return UUID(int=value)


def allocation(plan, library, owner) -> int:
    return next((item.allocated_bytes for item in plan.allocations if item.library_id == library and item.user_id == owner), 0)


def test_logical_accounting_is_canonical_utf8_and_counts_objects_exactly() -> None:
    first = logical_record_bytes("book", {"title": "Árbore", "pages": 10})
    second = logical_record_bytes("book", {"pages": 10, "title": "Árbore"})
    assert first == second
    assert logical_collection_bytes([("book", {"title": "Árbore", "pages": 10})], object_bytes=[70_038]) == first + 70_038
    with pytest.raises(StorageRuleViolation):
        logical_collection_bytes([], object_bytes=[-1])


def test_free_beta_entitlement_is_decimal_100_mb() -> None:
    assert ACCOUNT_QUOTA_BYTES == 100_000_000
    assert AccountCapacity(uid(1)).entitlement_bytes == 100_000_000


def test_equal_capacity_is_balanced_and_every_byte_is_charged_once() -> None:
    library = uid(10); first = uid(1); second = uid(2)
    plan = allocate_storage(
        [AccountCapacity(first), AccountCapacity(second)],
        [LibraryDemand(library, 81, (first, second))],
    )
    shares = [allocation(plan, library, first), allocation(plan, library, second)]
    assert sum(shares) == 81
    assert max(shares) - min(shares) <= 1


def test_global_solver_shifts_shared_bytes_to_the_owner_with_capacity() -> None:
    ana, luis, mohammed = uid(1), uid(2), uid(3)
    first_library, second_library = uid(10), uid(11)
    plan = allocate_storage(
        [
            AccountCapacity(ana, 300, 250),
            AccountCapacity(luis, 300, 190),
            AccountCapacity(mohammed, 300, 50),
        ],
        [
            LibraryDemand(first_library, 80, (ana, luis)),
            LibraryDemand(second_library, 300, (luis, mohammed)),
        ],
        {(first_library, ana): 40, (first_library, luis): 40,
         (second_library, luis): 50, (second_library, mohammed): 50},
    )
    assert allocation(plan, first_library, ana) == 40
    assert allocation(plan, first_library, luis) == 40
    assert allocation(plan, second_library, luis) == 70
    assert allocation(plan, second_library, mohammed) == 230
    assert plan.account_used_bytes == {ana: 290, luis: 300, mohammed: 280}


def test_prior_allocation_is_retained_when_feasible() -> None:
    library = uid(10); first = uid(1); second = uid(2)
    plan = allocate_storage(
        [AccountCapacity(first, 100), AccountCapacity(second, 100)],
        [LibraryDemand(library, 80, (first, second))],
        {(library, first): 60, (library, second): 20},
    )
    assert allocation(plan, library, first) == 60
    assert allocation(plan, library, second) == 20


def test_infeasible_or_invalid_inputs_fail_without_exposing_an_owner() -> None:
    first, second, library = uid(1), uid(2), uid(10)
    with pytest.raises(InsufficientSharedCapacity, match="Shared storage capacity is insufficient"):
        allocate_storage(
            [AccountCapacity(first, 20), AccountCapacity(second, 20)],
            [LibraryDemand(library, 41, (first, second))],
        )
    with pytest.raises(StorageRuleViolation):
        allocate_storage([AccountCapacity(first)], [LibraryDemand(library, 1, ())])
