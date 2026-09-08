from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bookpile_server.models import (
    AccountStorageEntitlement,
    Library,
    LibraryDeletionTombstone,
    LibraryMembership,
    LibraryStorageAllocation,
    LibraryStorageUsage,
    User,
    UserProfile,
    UserProfileFieldVisibility,
)


def fixture_account(session: Session, suffix: str = "one") -> User:
    user = User(
        email=f"schema-{suffix}@example.test",
        username=f"schema_{suffix}",
        password_hash="not-a-real-hash",
        state="active",
    )
    session.add(user)
    session.flush()
    return user


def test_profile_gender_shape_and_visibility_are_database_guarded(session: Session) -> None:
    user = fixture_account(session)
    session.add_all(
        [
            UserProfile(
                user_id=user.id,
                gender="CUSTOM",
                custom_gender="Non-binary",
                preferred_pronoun="NEUTRAL",
                neutral_pronoun="they",
            ),
            UserProfileFieldVisibility(
                user_id=user.id,
                field_name="city",
                visibility="SHARED_LIBRARY_MEMBERS",
            ),
        ]
    )
    session.commit()

    invalid_user = fixture_account(session, "invalid")
    session.add(
        UserProfile(
            user_id=invalid_user.id,
            gender="MALE",
            preferred_pronoun="MALE",
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_allocation_requires_membership_and_non_negative_bytes(session: Session) -> None:
    owner = fixture_account(session)
    outsider = fixture_account(session, "outsider")
    library = Library(name="Schema library", slug="schema-library")
    session.add(library)
    session.flush()
    session.add(
        LibraryMembership(library_id=library.id, user_id=owner.id, role="OWNER")
    )
    session.commit()

    session.add_all(
        [
            AccountStorageEntitlement(user_id=owner.id),
            LibraryStorageUsage(
                library_id=library.id,
                logical_size_bytes=50,
                accounting_version=1,
                revision=0,
            ),
            LibraryStorageAllocation(
                library_id=library.id, user_id=owner.id, allocated_bytes=50
            ),
        ]
    )
    session.commit()

    session.add(
        LibraryStorageAllocation(
            library_id=library.id, user_id=outsider.id, allocated_bytes=1
        )
    )
    with pytest.raises(IntegrityError):
        session.commit()


def test_tombstone_survives_without_live_library_foreign_key(session: Session) -> None:
    owner = fixture_account(session)
    now = datetime.now(UTC)
    tombstone = LibraryDeletionTombstone(
        library_id=uuid4(),
        library_name="Deleted library",
        requested_by_user_id=owner.id,
        logical_size_bytes=123,
        membership_snapshot=[{"user_id": str(owner.id), "role": "OWNER"}],
        allocation_snapshot=[{"user_id": str(owner.id), "bytes": 123}],
        object_manifest=[],
        created_at=now,
        recover_until=now + timedelta(hours=48),
    )
    session.add(tombstone)
    session.commit()
    assert tombstone.state == "PENDING"
