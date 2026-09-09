from datetime import UTC, datetime, timedelta
from uuid import uuid4
from urllib.parse import parse_qs, urlparse

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bookpile_server.config import get_settings
from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.email_delivery import EmailDeliveryError
from bookpile_server.models import (
    AccountDeletionTombstone,
    Library,
    LibraryMembership,
    User,
    UserProfileImage,
    UserSession,
)
from bookpile_server.security.passwords import hash_password
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.services.library_deletion_cleanup import (
    finalize_expired_account_deletions,
)


PASSWORD = "a valid account password"
CSRF = "account-deletion-csrf"


def add_user(session: Session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash=hash_password(PASSWORD),
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.commit()
    return user


def authenticate(client: TestClient, session: Session, user: User) -> None:
    now = datetime.now(UTC)
    token = f"account-delete-{uuid4().hex}"
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_secret(token),
            csrf_token_hash=hash_session_secret(CSRF),
            last_seen_at=now,
            expires_at=now + timedelta(days=7),
            absolute_expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, token)
    client.cookies.set(settings.csrf_cookie_name, CSRF)


def csrf() -> dict[str, str]:
    return {"X-CSRF-Token": CSRF}


def delete_payload(username: str, password: str = PASSWORD) -> dict[str, object]:
    return {
        "current_password": password,
        "confirmation_username": username,
        "acknowledge_permanent_deletion": True,
    }


def test_owner_must_resolve_active_library_ownership_first(
    client: TestClient, session: Session
) -> None:
    owner = add_user(session, "account_owner")
    library = Library(name="Owner Library", slug="owner-library", created_by_user_id=owner.id)
    session.add(library)
    session.flush()
    session.add(LibraryMembership(library_id=library.id, user_id=owner.id, role="OWNER"))
    session.commit()
    authenticate(client, session, owner)

    response = client.request(
        "DELETE", "/api/v1/account", json=delete_payload(owner.username), headers=csrf()
    )

    assert response.status_code == 409
    assert "Owner Library" in response.json()["detail"]
    session.refresh(owner)
    assert owner.state == "active"


def test_deleted_viewer_is_locked_out_and_can_restore_membership_only_by_email_link(
    client: TestClient, session: Session, email_sender
) -> None:
    owner = add_user(session, "remaining_owner")
    viewer = add_user(session, "recovering_viewer")
    library = Library(name="Shared Account Test", slug="shared-account-test", created_by_user_id=owner.id)
    session.add(library)
    session.flush()
    session.add_all([
        LibraryMembership(library_id=library.id, user_id=owner.id, role="OWNER", selected_reading_user_id=owner.id),
        LibraryMembership(library_id=library.id, user_id=viewer.id, role="VIEWER", viewer_scope="CATALOG_AND_MAP", selected_reading_user_id=owner.id),
    ])
    session.commit()
    authenticate(client, session, viewer)

    deleted = client.request(
        "DELETE", "/api/v1/account", json=delete_payload(viewer.username), headers=csrf()
    )
    assert deleted.status_code == 200
    assert client.get("/api/v1/auth/me").status_code == 401
    assert session.query(LibraryMembership).filter_by(user_id=viewer.id).count() == 0

    pending_login = client.post(
        "/api/v1/auth/login",
        json={"identifier": viewer.username, "password": PASSWORD, "remember_me": False},
    )
    assert pending_login.status_code == 401
    assert pending_login.json()["detail"] == "Invalid credentials"
    wrong = client.post(
        "/api/v1/auth/account-deletion/restore",
        json={"token": "x" * 43},
    )
    assert wrong.status_code == 400
    assert len(email_sender.emails) == 1
    recovery_url = email_sender.emails[0].text.split("\n\n")[2]
    recovery_token = parse_qs(urlparse(recovery_url).query)["token"][0]
    tombstone = session.query(AccountDeletionTombstone).filter_by(user_id=viewer.id).one()
    assert tombstone.recovery_token_hash != recovery_token
    assert len(tombstone.recovery_token_hash or "") == 64
    restored = client.post(
        "/api/v1/auth/account-deletion/restore",
        json={"token": recovery_token},
    )
    assert restored.status_code == 204
    assert client.post(
        "/api/v1/auth/account-deletion/restore",
        json={"token": recovery_token},
    ).status_code == 400
    session.refresh(viewer)
    assert viewer.state == "active"
    membership = session.query(LibraryMembership).filter_by(user_id=viewer.id).one()
    assert membership.viewer_scope == "CATALOG_AND_MAP"
    assert client.post(
        "/api/v1/auth/login",
        json={"identifier": viewer.username, "password": PASSWORD, "remember_me": False},
    ).status_code == 200


def test_expired_account_cleanup_erases_user_object_and_tombstone_identity(
    session: Session, tmp_path
) -> None:
    user = add_user(session, "expired_account")
    now = datetime.now(UTC)
    storage = FilesystemCoverStorage(tmp_path / "private")
    storage.put("profile-images/expired.webp", b"image")
    session.add(UserProfileImage(
        user_id=user.id,
        object_key="profile-images/expired.webp",
        media_type="image/webp",
        byte_size=5,
        width_px=1,
        height_px=1,
        sha256="0" * 64,
    ))
    tombstone = AccountDeletionTombstone(
        user_id=user.id,
        username=user.username,
        email=user.email,
        membership_snapshot=[],
        object_manifest=[{"object_key": "profile-images/expired.webp", "byte_size": 5}],
        created_at=now - timedelta(hours=2),
        recover_until=now - timedelta(hours=1),
    )
    user.state = "pending_deletion"
    session.add(tombstone)
    session.commit()

    assert finalize_expired_account_deletions(session, storage, now=now) == 1
    assert session.get(User, user.id) is None
    finalized = session.get(AccountDeletionTombstone, tombstone.id)
    assert finalized.state == "FINALIZED"
    assert finalized.username is None and finalized.email is None
    assert finalized.membership_snapshot == [] and finalized.object_manifest == []


def test_account_is_not_deleted_when_recovery_email_cannot_be_sent(
    client: TestClient, session: Session, email_sender
) -> None:
    user = add_user(session, "mail_failure")
    authenticate(client, session, user)

    def fail(_email) -> None:
        raise EmailDeliveryError("Email delivery failed.")

    email_sender.send = fail
    response = client.request(
        "DELETE", "/api/v1/account", json=delete_payload(user.username), headers=csrf()
    )

    assert response.status_code == 503
    session.refresh(user)
    assert user.state == "active"
    assert session.query(AccountDeletionTombstone).filter_by(user_id=user.id).count() == 0
