from io import BytesIO
from pathlib import Path
from uuid import UUID, uuid4

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.api.dependencies import get_profile_image_service
from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.models import (
    AccountStorageEntitlement,
    Book,
    Library,
    LibraryMembership,
    User,
    UserProfile,
    UserProfileFieldVisibility,
    UserProfileImage,
)
from bookpile_server.repositories.profiles import ProfileRepository
from bookpile_server.repositories.storage import StorageRepository
from bookpile_server.services.profiles import ProfileImageService
from bookpile_server.services.storage import StorageService
from test_catalogue_services import CSRF, add_user, authenticate
from test_profiles_api import profile_payload


PROFILE_KEYS = {
    "user_id",
    "username",
    "display_name",
    "timezone",
    "gender",
    "custom_gender",
    "preferred_pronoun",
    "neutral_pronoun",
    "city",
    "state",
    "country",
    "date_of_birth",
    "profile_image_visible",
    "visibilities",
}
STORAGE_KEYS = {
    "libraries",
    "account_data_share_of_used",
    "account_data_share_of_entitlement",
    "used_share_of_entitlement",
}
LIBRARY_STORAGE_KEYS = {
    "library_id",
    "name",
    "colour_key",
    "share_of_used",
    "share_of_entitlement",
}


def _membership(
    library: Library,
    user_id: UUID,
    role: str,
    viewer_scope: str | None = None,
) -> LibraryMembership:
    return LibraryMembership(
        library_id=library.id,
        user_id=user_id,
        role=role,
        viewer_scope=viewer_scope,
    )


def _assert_profile_shape(body: dict[str, object]) -> None:
    assert set(body) == PROFILE_KEYS
    serialized = str(body).lower()
    for forbidden in (
        "email",
        "password",
        "session",
        "entitlement",
        "allocation",
        "object_key",
        "sha256",
        "plan_code",
        "created_at",
        "updated_at",
    ):
        assert forbidden not in serialized


def _stored_profile(session: Session, user_id: UUID) -> tuple[object, ...]:
    profile = session.get(UserProfile, user_id)
    assert profile is not None
    values = tuple(getattr(profile, column.name) for column in UserProfile.__table__.columns)
    visibility = tuple(
        session.execute(
            select(
                UserProfileFieldVisibility.field_name,
                UserProfileFieldVisibility.visibility,
            )
            .where(UserProfileFieldVisibility.user_id == user_id)
            .order_by(UserProfileFieldVisibility.field_name)
        ).all()
    )
    return values, visibility


def test_private_account_identity_is_never_a_discovery_projection(
    client: TestClient,
    session: Session,
) -> None:
    target = add_user(session, "a8_private_identity")
    outsider = add_user(session, "a8_private_outsider")
    session.commit()

    client.cookies.clear()
    assert client.get("/api/v1/account").status_code == 401
    assert client.get(f"/api/v1/profiles/{target.id}").status_code == 401
    assert client.get("/api/v1/account/storage").status_code == 401

    expected_keys = {
        "user_id",
        "username",
        "email",
        "created_at",
        "password_protected",
    }
    for actor in (target, outsider):
        authenticate(client, session, actor)
        response = client.get("/api/v1/account")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == expected_keys
        assert body["user_id"] == str(actor.id)
        assert body["username"] == actor.username
        assert body["email"] == actor.email
        assert body["password_protected"] is True
        serialized = response.text.lower()
        for forbidden in (
            "password_hash",
            "email_verified_at",
            "session",
            "state",
            "entitlement",
            "allocation",
            "plan_code",
            "object_key",
        ):
            assert forbidden not in serialized
        other: User = outsider if actor is target else target
        assert other.email not in response.text


def test_profile_projection_and_image_follow_only_explicit_visibility(
    client: TestClient,
    session: Session,
    tmp_path: Path,
) -> None:
    target = add_user(session, "a8_profile_target")
    coowner = add_user(session, "a8_profile_coowner")
    catalogue_viewer = add_user(session, "a8_catalogue_viewer")
    map_viewer = add_user(session, "a8_map_viewer")
    foreign_owner = add_user(session, "a8_foreign_owner")
    outsider = add_user(session, "a8_profile_outsider")
    shared = Library(name="A8 shared", slug="a8-shared", created_by_user_id=target.id)
    foreign = Library(
        name="A8 foreign",
        slug="a8-foreign",
        created_by_user_id=foreign_owner.id,
    )
    session.add_all((shared, foreign))
    session.flush()
    session.add_all(
        (
            _membership(shared, target.id, "OWNER"),
            _membership(shared, coowner.id, "OWNER"),
            _membership(shared, catalogue_viewer.id, "VIEWER", "CATALOG_ONLY"),
            _membership(shared, map_viewer.id, "VIEWER", "CATALOG_AND_MAP"),
            _membership(foreign, foreign_owner.id, "OWNER"),
        )
    )
    session.commit()

    object_root = tmp_path / "a8-profile-objects"
    storage = FilesystemCoverStorage(object_root)
    client.app.dependency_overrides[get_profile_image_service] = lambda: (
        ProfileImageService(ProfileRepository(session), storage)
    )

    authenticate(client, session, target)
    saved = client.put(
        "/api/v1/account/profile",
        json=profile_payload(),
        headers={"X-CSRF-Token": CSRF},
    )
    assert saved.status_code == 200, saved.text
    own_body = saved.json()
    _assert_profile_shape(own_body)
    assert own_body["visibilities"] == {
        "display_name": "SHARED_LIBRARY_MEMBERS",
        "timezone": "PRIVATE",
        "personal_data": "SHARED_LIBRARY_MEMBERS",
        "profile_image": "AUTHENTICATED",
    }

    source = BytesIO()
    Image.new("RGB", (40, 40), "navy").save(source, format="JPEG")
    uploaded = client.put(
        "/api/v1/account/profile/image",
        files={"image": ("portrait.jpg", source.getvalue(), "image/jpeg")},
        headers={"X-CSRF-Token": CSRF},
    )
    assert uploaded.status_code == 204, uploaded.text
    image_record = session.get(UserProfileImage, target.id)
    assert image_record is not None
    private_object_key = image_record.object_key
    private_digest = image_record.sha256

    for actor in (coowner, catalogue_viewer, map_viewer):
        authenticate(client, session, actor)
        response = client.get(f"/api/v1/profiles/{target.id}")
        assert response.status_code == 200
        body = response.json()
        _assert_profile_shape(body)
        assert body["display_name"] == "Robin Reader"
        assert body["timezone"] is None
        assert body["gender"] == "CUSTOM"
        assert body["city"] == "Vigo"
        assert body["preferred_pronoun"] == "NEUTRAL"
        assert body["neutral_pronoun"] == "they"
        assert body["profile_image_visible"] is True
        assert body["visibilities"] is None
        image = client.get(f"/api/v1/profiles/{target.id}/image")
        assert image.status_code == 200
        assert image.headers["content-type"] == "image/webp"
        assert private_object_key not in response.text
        assert private_digest not in response.text

    for actor in (foreign_owner, outsider):
        authenticate(client, session, actor)
        response = client.get(f"/api/v1/profiles/{target.id}")
        assert response.status_code == 200
        body = response.json()
        _assert_profile_shape(body)
        assert body["username"] == target.username
        assert body["display_name"] is None
        assert body["timezone"] is None
        assert body["gender"] is None
        assert body["custom_gender"] is None
        assert body["city"] is None
        assert body["state"] is None
        assert body["country"] is None
        assert body["date_of_birth"] is None
        assert body["preferred_pronoun"] == "NEUTRAL"
        assert body["neutral_pronoun"] == "they"
        assert body["profile_image_visible"] is True
        assert body["visibilities"] is None
        assert target.email not in response.text

    authenticate(client, session, target)
    private_image_payload = profile_payload()
    private_image_payload["visibilities"]["profile_image"] = "PRIVATE"
    assert client.put(
        "/api/v1/account/profile",
        json=private_image_payload,
        headers={"X-CSRF-Token": CSRF},
    ).status_code == 200
    authenticate(client, session, outsider)
    private_projection = client.get(f"/api/v1/profiles/{target.id}")
    assert private_projection.json()["profile_image_visible"] is False
    assert client.get(f"/api/v1/profiles/{target.id}/image").status_code == 404
    authenticate(client, session, target)
    assert client.get(f"/api/v1/profiles/{target.id}/image").status_code == 200

    profile_before = _stored_profile(session, target.id)
    target.state = "pending_deletion"
    session.commit()
    for actor in (coowner, outsider):
        authenticate(client, session, actor)
        assert client.get(f"/api/v1/profiles/{target.id}").status_code == 404
        assert client.get(f"/api/v1/profiles/{uuid4()}").status_code == 404
    assert _stored_profile(session, target.id) == profile_before


def test_storage_overview_is_account_private_and_aggregate_only(
    client: TestClient,
    session: Session,
) -> None:
    owner = add_user(session, "a8_storage_owner")
    coowner = add_user(session, "a8_storage_coowner")
    viewer = add_user(session, "a8_storage_viewer")
    foreign_owner = add_user(session, "a8_storage_foreign")
    outsider = add_user(session, "a8_storage_outsider")
    shared = Library(
        name="A8 private capacity",
        slug="a8-private-capacity",
        created_by_user_id=owner.id,
    )
    foreign = Library(
        name="A8 foreign capacity",
        slug="a8-foreign-capacity",
        created_by_user_id=foreign_owner.id,
    )
    session.add_all((shared, foreign))
    session.flush()
    session.add_all(
        (
            _membership(shared, owner.id, "OWNER"),
            _membership(shared, coowner.id, "OWNER"),
            _membership(shared, viewer.id, "VIEWER", "CATALOG_ONLY"),
            _membership(foreign, foreign_owner.id, "OWNER"),
            Book(
                library_id=shared.id,
                title="Shared capacity book",
                author="A8 author",
            ),
            Book(
                library_id=foreign.id,
                title="Foreign capacity book",
                author="A8 author",
            ),
        )
    )
    for user in (owner, coowner, viewer, foreign_owner, outsider):
        session.add(AccountStorageEntitlement(user_id=user.id))
    session.commit()
    StorageService(StorageRepository(session)).rebuild_owned_library_usage()

    expectations = (
        (owner, {str(shared.id)}, {shared.name}, {foreign.name}),
        (coowner, {str(shared.id)}, {shared.name}, {foreign.name}),
        (viewer, set(), set(), {shared.name, foreign.name}),
        (foreign_owner, {str(foreign.id)}, {foreign.name}, {shared.name}),
        (outsider, set(), set(), {shared.name, foreign.name}),
    )
    for actor, expected_ids, expected_names, forbidden_names in expectations:
        authenticate(client, session, actor)
        response = client.get("/api/v1/account/storage")
        assert response.status_code == 200
        body = response.json()
        assert set(body) == STORAGE_KEYS
        assert all(set(item) == LIBRARY_STORAGE_KEYS for item in body["libraries"])
        assert {item["library_id"] for item in body["libraries"]} == expected_ids
        assert {item["name"] for item in body["libraries"]} == expected_names
        serialized = response.text.lower()
        for forbidden in (
            "byte",
            "limit",
            "plan_code",
            "allocation",
            "logical_size",
            "object_key",
            "email",
            "password",
            "session",
        ):
            assert forbidden not in serialized
        assert all(name not in response.text for name in forbidden_names)
        assert all(
            other.email not in response.text
            for other in (owner, coowner, viewer, foreign_owner, outsider)
        )
