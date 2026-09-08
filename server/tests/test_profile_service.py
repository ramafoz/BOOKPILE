from sqlalchemy.orm import Session

from bookpile_server.models import (
    Library,
    LibraryMembership,
    User,
    UserProfile,
    UserProfileFieldVisibility,
)
from bookpile_server.repositories.profiles import ProfileRepository
from bookpile_server.services.profiles import ProfileService


def user(session: Session, suffix: str) -> User:
    item = User(
        email=f"profile-{suffix}@example.test",
        username=f"profile_{suffix}",
        password_hash="not-a-real-hash",
        state="active",
    )
    session.add(item)
    session.flush()
    return item


def test_projection_is_field_scoped_and_pronouns_remain_authenticated(session: Session) -> None:
    target = user(session, "target")
    member = user(session, "member")
    outsider = user(session, "outsider")
    library = Library(name="Shared", slug="profile-shared")
    session.add(library)
    session.flush()
    session.add_all(
        [
            LibraryMembership(library_id=library.id, user_id=target.id, role="OWNER"),
            LibraryMembership(
                library_id=library.id,
                user_id=member.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
            ),
            UserProfile(
                user_id=target.id,
                display_name="Visible to members",
                city="Visible to everyone",
                gender="CUSTOM",
                custom_gender="Private gender",
                preferred_pronoun="NEUTRAL",
                neutral_pronoun="they",
            ),
            UserProfileFieldVisibility(
                user_id=target.id,
                field_name="display_name",
                visibility="SHARED_LIBRARY_MEMBERS",
            ),
            UserProfileFieldVisibility(
                user_id=target.id,
                field_name="city",
                visibility="AUTHENTICATED",
            ),
        ]
    )
    session.commit()
    service = ProfileService(ProfileRepository(session))

    member_view = service.project(target_user_id=target.id, actor_user_id=member.id)
    assert member_view.display_name == "Visible to members"
    assert member_view.city == "Visible to everyone"
    assert member_view.gender is None
    assert member_view.preferred_pronoun == "NEUTRAL"
    assert member_view.neutral_pronoun == "they"

    outsider_view = service.project(target_user_id=target.id, actor_user_id=outsider.id)
    assert outsider_view.display_name is None
    assert outsider_view.city == "Visible to everyone"
    assert outsider_view.preferred_pronoun == "NEUTRAL"

    own_view = service.project(target_user_id=target.id, actor_user_id=target.id)
    assert own_view.gender == "CUSTOM"
    assert own_view.display_name == "Visible to members"
