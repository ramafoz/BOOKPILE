from datetime import UTC, datetime

import pytest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from bookpile_server.models import Library, LibraryMembership, User


def add_user(session: Session, username: str) -> User:
    username = username.lower()
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash="not-used-by-membership-tests",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    return user


def test_library_accepts_equal_owners_and_scoped_viewers(session: Session) -> None:
    first_owner = add_user(session, "first_owner")
    second_owner = add_user(session, "second_owner")
    viewer = add_user(session, "catalogue_viewer")
    library = Library(
        name="Shared home",
        slug="shared-home",
        created_by_user_id=first_owner.id,
    )
    session.add(library)
    session.flush()
    session.add_all(
        [
            LibraryMembership(
                library_id=library.id,
                user_id=first_owner.id,
                role="OWNER",
                selected_reading_user_id=first_owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=second_owner.id,
                role="OWNER",
                selected_reading_user_id=second_owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
                selected_reading_user_id=first_owner.id,
            ),
        ]
    )

    session.commit()

    assert {membership.role for membership in library.memberships} == {
        "OWNER",
        "VIEWER",
    }


@pytest.mark.parametrize(
    ("role", "scope"),
    [
        ("OWNER", "CATALOG_ONLY"),
        ("VIEWER", None),
        ("EDITOR", None),
        ("VIEWER", "MAP_ONLY"),
    ],
)
def test_database_rejects_invalid_role_scope_combinations(
    session: Session, role: str, scope: str | None
) -> None:
    user = add_user(session, f"invalid_{role.lower()}_{scope or 'none'}")
    library = Library(name="Invalid test", slug=f"invalid-{user.username}")
    session.add(library)
    session.flush()
    session.add(
        LibraryMembership(
            library_id=library.id,
            user_id=user.id,
            role=role,
            viewer_scope=scope,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()


def test_database_rejects_duplicate_membership(session: Session) -> None:
    user = add_user(session, "only_once")
    library = Library(name="One membership", slug="one-membership")
    session.add(library)
    session.flush()
    session.add_all(
        [
            LibraryMembership(
                library_id=library.id, user_id=user.id, role="OWNER"
            ),
            LibraryMembership(
                library_id=library.id, user_id=user.id, role="OWNER"
            ),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()
