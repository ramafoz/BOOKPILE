from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..models import (
    AccountStorageEntitlement,
    Library,
    LibraryMembership,
    LibraryStorageAllocation,
    LibraryStorageUsage,
    User,
)


class StorageRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def lock_entitlements(self) -> list[AccountStorageEntitlement]:
        return list(
            self.session.scalars(
                select(AccountStorageEntitlement)
                .order_by(AccountStorageEntitlement.user_id)
                .with_for_update()
            )
        )

    def ensure_entitlements(self) -> list[AccountStorageEntitlement]:
        entitled = {item.user_id: item for item in self.lock_entitlements()}
        for user_id in self.session.scalars(select(User.id).order_by(User.id)):
            if user_id not in entitled:
                item = AccountStorageEntitlement(user_id=user_id)
                self.session.add(item)
                entitled[user_id] = item
        self.session.flush()
        return list(entitled.values())

    def lock_owner_memberships(self) -> list[LibraryMembership]:
        return list(
            self.session.scalars(
                select(LibraryMembership)
                .join(Library)
                .where(LibraryMembership.role == "OWNER", Library.state == "active")
                .order_by(LibraryMembership.library_id, LibraryMembership.user_id)
                .with_for_update(of=LibraryMembership)
            )
        )

    def lock_usage(self) -> list[LibraryStorageUsage]:
        return list(
            self.session.scalars(
                select(LibraryStorageUsage)
                .order_by(LibraryStorageUsage.library_id)
                .with_for_update()
            )
        )

    def lock_allocations(self) -> list[LibraryStorageAllocation]:
        return list(
            self.session.scalars(
                select(LibraryStorageAllocation)
                .order_by(
                    LibraryStorageAllocation.library_id,
                    LibraryStorageAllocation.user_id,
                )
                .with_for_update()
            )
        )

    def replace_allocations(self, allocations) -> None:
        self.session.execute(delete(LibraryStorageAllocation))
        self.session.add_all(allocations)

    def entitlement_for_user(self, user_id: UUID) -> AccountStorageEntitlement | None:
        return self.session.get(AccountStorageEntitlement, user_id)

    def allocations_for_user(
        self, user_id: UUID
    ) -> list[tuple[LibraryStorageAllocation, Library]]:
        return list(
            self.session.execute(
                select(LibraryStorageAllocation, Library)
                .join(Library, Library.id == LibraryStorageAllocation.library_id)
                .where(
                    LibraryStorageAllocation.user_id == user_id,
                    Library.state == "active",
                )
                .order_by(Library.name, Library.id)
            ).all()
        )

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
