from sqlalchemy import func, select
from sqlalchemy.orm import Session

from bookpile_server.models import (
    AccountStorageEntitlement,
    Book,
    Library,
    LibraryMembership,
    LibraryStorageAllocation,
    LibraryStorageUsage,
    User,
)
from bookpile_server.repositories.storage import StorageRepository
from bookpile_server.services.storage import StorageService
from bookpile_server.services.storage_accounting import calculate_library_logical_bytes


def make_owner(session: Session, suffix: str) -> User:
    user = User(
        email=f"storage-{suffix}@example.test",
        username=f"storage_{suffix}",
        password_hash="not-a-real-hash",
        state="active",
    )
    session.add(user)
    session.flush()
    return user


def test_rebuild_accounts_owned_libraries_and_ignores_unowned_seed(session: Session) -> None:
    owner = make_owner(session, "owner")
    shared_owner = make_owner(session, "shared")
    owned = Library(name="Owned", slug="owned-storage")
    unowned = Library(name="Seed", slug="unowned-seed")
    session.add_all([owned, unowned])
    session.flush()
    session.add_all(
        [
            LibraryMembership(library_id=owned.id, user_id=owner.id, role="OWNER"),
            LibraryMembership(library_id=owned.id, user_id=shared_owner.id, role="OWNER"),
            Book(library_id=owned.id, title="Book", author="Author"),
        ]
    )
    session.commit()

    expected = calculate_library_logical_bytes(session, owned.id)
    StorageService(StorageRepository(session)).rebuild_owned_library_usage()

    usage = session.get(LibraryStorageUsage, owned.id)
    assert usage is not None
    assert usage.logical_size_bytes == expected
    assert session.get(LibraryStorageUsage, unowned.id) is None
    assert session.scalar(select(func.count()).select_from(AccountStorageEntitlement)) == 2
    allocations = list(
        session.scalars(
            select(LibraryStorageAllocation).where(
                LibraryStorageAllocation.library_id == owned.id
            )
        )
    )
    assert sum(item.allocated_bytes for item in allocations) == expected
    assert max(item.allocated_bytes for item in allocations) - min(
        item.allocated_bytes for item in allocations
    ) <= 1


def test_rebuild_updates_revision_and_preserves_allocation_total(session: Session) -> None:
    owner = make_owner(session, "revision")
    library = Library(name="Revision", slug="revision-storage")
    session.add(library)
    session.flush()
    session.add(LibraryMembership(library_id=library.id, user_id=owner.id, role="OWNER"))
    session.commit()
    service = StorageService(StorageRepository(session))
    service.rebuild_owned_library_usage()
    initial = session.get(LibraryStorageUsage, library.id)
    assert initial is not None and initial.revision == 0

    session.add(Book(library_id=library.id, title="Larger", author="Author"))
    session.commit()
    service.rebuild_owned_library_usage()
    session.refresh(initial)
    allocation = session.get(LibraryStorageAllocation, (library.id, owner.id))
    assert initial.revision == 1
    assert allocation is not None
    assert allocation.allocated_bytes == initial.logical_size_bytes
