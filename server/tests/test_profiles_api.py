from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from bookpile_server.models import AccountStorageEntitlement
from bookpile_server.repositories.storage import StorageRepository
from bookpile_server.services.storage import StorageService
from test_catalogue_services import (
    add_user,
    authenticate,
    create_library_with_members,
    csrf,
)


def profile_payload() -> dict[str, object]:
    return {
        "display_name": "Robin Reader",
        "timezone": "Europe/Madrid",
        "gender": "CUSTOM",
        "custom_gender": "Non-binary",
        "preferred_pronoun": "NEUTRAL",
        "neutral_pronoun": "they",
        "city": "Vigo",
        "state": "Galicia",
        "country": "Spain",
        "date_of_birth": "1990-04-12",
        "visibilities": {
            "display_name": "SHARED_LIBRARY_MEMBERS",
            "timezone": "PRIVATE",
            "personal_data": "SHARED_LIBRARY_MEMBERS",
            "profile_image": "AUTHENTICATED",
        },
    }


def test_profile_update_and_projection_respect_field_privacy(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "profile_api_owner")
    member = add_user(session, "profile_api_member")
    outsider = add_user(session, "profile_api_outsider")
    session.add_all(
        [
            AccountStorageEntitlement(user_id=owner.id),
            AccountStorageEntitlement(user_id=member.id),
            AccountStorageEntitlement(user_id=outsider.id),
        ]
    )
    session.commit()
    create_library_with_members(session, owner, member)
    authenticate(client, session, owner)

    saved = client.put("/api/v1/account/profile", json=profile_payload(), headers=csrf())
    assert saved.status_code == 200, saved.text
    assert saved.json()["gender"] == "CUSTOM"
    assert saved.json()["visibilities"]["personal_data"] == "SHARED_LIBRARY_MEMBERS"

    authenticate(client, session, member)
    member_view = client.get(f"/api/v1/profiles/{owner.id}")
    assert member_view.status_code == 200
    assert member_view.json()["display_name"] == "Robin Reader"
    assert member_view.json()["state"] == "Galicia"
    assert member_view.json()["gender"] == "CUSTOM"
    assert member_view.json()["preferred_pronoun"] == "NEUTRAL"

    authenticate(client, session, outsider)
    outsider_view = client.get(f"/api/v1/profiles/{owner.id}").json()
    assert outsider_view["display_name"] is None
    assert outsider_view["state"] is None
    assert outsider_view["city"] is None
    assert outsider_view["neutral_pronoun"] == "they"


def test_private_account_and_password_change(client: TestClient, session: Session) -> None:
    owner = add_user(session, "private_account_owner")
    session.commit()
    authenticate(client, session, owner)

    account = client.get("/api/v1/account")
    assert account.status_code == 200
    assert account.json()["username"] == owner.username
    assert account.json()["email"] == owner.email
    assert "password_hash" not in account.text

    changed = client.put(
        "/api/v1/account/password",
        json={
            "current_password": "valid catalogue password",
            "new_password": "a different valid password 🔐",
            "confirmation": "a different valid password 🔐",
        },
        headers=csrf(),
    )
    assert changed.status_code == 204, changed.text


def test_non_custom_gender_discards_stale_pronoun_details(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "profile_gender_owner")
    session.commit()
    authenticate(client, session, owner)
    payload = profile_payload()
    payload.update(
        gender="MALE",
        custom_gender="stale custom value",
        preferred_pronoun="MALE",
        neutral_pronoun=None,
    )

    saved = client.put("/api/v1/account/profile", json=payload, headers=csrf())

    assert saved.status_code == 200, saved.text
    assert saved.json()["gender"] == "MALE"
    assert saved.json()["custom_gender"] is None
    assert saved.json()["preferred_pronoun"] is None


def test_private_storage_response_contains_proportions_not_byte_values(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "storage_api_owner")
    session.add(AccountStorageEntitlement(user_id=owner.id))
    session.commit()
    create_library_with_members(session, owner)
    StorageService(StorageRepository(session)).rebuild_owned_library_usage()
    authenticate(client, session, owner)

    response = client.get("/api/v1/account/storage")
    assert response.status_code == 200
    body = response.json()
    assert len(body["libraries"]) == 1
    assert 0 < body["used_share_of_entitlement"] < 1
    serialized = response.text.lower()
    assert "byte" not in serialized
    assert "limit" not in serialized
    assert "entitlement_bytes" not in serialized


def test_profile_image_is_private_processed_and_removable(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "profile_image_owner")
    outsider = add_user(session, "profile_image_outsider")
    session.add_all(
        [
            AccountStorageEntitlement(user_id=owner.id),
            AccountStorageEntitlement(user_id=outsider.id),
        ]
    )
    session.commit()
    authenticate(client, session, owner)
    client.put("/api/v1/account/profile", json=profile_payload(), headers=csrf())
    source = BytesIO()
    Image.new("RGB", (500, 500), "navy").save(source, format="JPEG")
    uploaded = client.put(
        "/api/v1/account/profile/image",
        files={"image": ("portrait.jpg", source.getvalue(), "image/jpeg")},
        headers=csrf(),
    )
    assert uploaded.status_code == 204, uploaded.text
    fetched = client.get(f"/api/v1/profiles/{owner.id}/image")
    assert fetched.status_code == 200
    assert fetched.headers["content-type"] == "image/webp"

    authenticate(client, session, outsider)
    assert client.get(f"/api/v1/profiles/{owner.id}/image").status_code == 200
    authenticate(client, session, owner)
    assert client.delete("/api/v1/account/profile/image", headers=csrf()).status_code == 204
    assert client.get(f"/api/v1/profiles/{owner.id}/image").status_code == 404
