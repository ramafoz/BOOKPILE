"""Transactional persistence boundary for logical storage allocations."""
from collections import defaultdict

from ..models import LibraryStorageAllocation, LibraryStorageUsage
from ..repositories.storage import StorageRepository
from .storage_accounting import calculate_account_data_bytes, calculate_library_logical_bytes
from .storage_domain import (
    AccountCapacity,
    LibraryDemand,
    LOGICAL_ACCOUNTING_VERSION,
    allocate_storage,
)


class StorageService:
    def __init__(self, repository: StorageRepository) -> None:
        self.repository = repository

    def rebuild_owned_library_usage(self) -> None:
        """Backfill all owned libraries and atomically replace their allocations."""
        try:
            self.prepare_owned_library_usage()
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            raise

    def prepare_owned_library_usage(self) -> None:
        """Reconcile inside the caller's transaction without committing it."""
        entitlements = self.repository.ensure_entitlements()
        memberships = self.repository.lock_owner_memberships()
        existing_usage = {item.library_id: item for item in self.repository.lock_usage()}
        previous = {
            (item.library_id, item.user_id): item.allocated_bytes
            for item in self.repository.lock_allocations()
        }
        owners = defaultdict(list)
        for membership in memberships:
            owners[membership.library_id].append(membership.user_id)

        demands = []
        for library_id, owner_ids in owners.items():
            size = calculate_library_logical_bytes(self.repository.session, library_id)
            usage = existing_usage.get(library_id)
            if usage is None:
                usage = LibraryStorageUsage(
                    library_id=library_id,
                    logical_size_bytes=size,
                    accounting_version=LOGICAL_ACCOUNTING_VERSION,
                    revision=0,
                )
                self.repository.session.add(usage)
            elif usage.logical_size_bytes != size or usage.accounting_version != LOGICAL_ACCOUNTING_VERSION:
                usage.logical_size_bytes = size
                usage.accounting_version = LOGICAL_ACCOUNTING_VERSION
                usage.revision += 1
            demands.append(
                LibraryDemand(
                    library_id=library_id,
                    logical_size_bytes=size,
                    owner_ids=tuple(owner_ids),
                )
            )

        capacities = [
            AccountCapacity(
                user_id=item.user_id,
                entitlement_bytes=item.limit_bytes,
                account_data_bytes=calculate_account_data_bytes(
                    self.repository.session, item.user_id
                ),
            )
            for item in entitlements
        ]
        plan = allocate_storage(capacities, demands, previous)
        self.repository.replace_allocations(
            [
                LibraryStorageAllocation(
                    library_id=item.library_id,
                    user_id=item.user_id,
                    allocated_bytes=item.allocated_bytes,
                )
                for item in plan.allocations
            ]
        )
