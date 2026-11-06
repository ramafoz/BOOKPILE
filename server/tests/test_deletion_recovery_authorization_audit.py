from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlparse
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.models import (
    AccountDeletionTombstone,
    Library,
    LibraryDeletionTombstone,
    LibraryMembership,
    User,
    UserProfileImage,
    UserSession,
)
from bookpile_server.services.library_deletion_cleanup import (
    finalize_expired_account_deletions,
)
from test_account_deletion import (
    CSRF as ACCOUNT_CSRF,
    add_user as add_account_user,
    authenticate as authenticate_account,
    csrf as account_csrf,
    delete_payload as account_delete_payload,
)
from test_libraries_api import (
    CSRF as LIBRARY_CSRF,
    PASSWORD as LIBRARY_PASSWORD,
    add_user as add_library_user,
    authenticate as authenticate_library,
    csrf_headers as library_csrf,
)


def _library_tombstone_snapshot(tombstone: LibraryDeletionTombstone) -> tuple[object, ...]:
    recover_until = tombstone.recover_until
    recovered_at = tombstone.recovered_at
    return (
        tombstone.state,
        tombstone.library_id,
        tombstone.library_name,
        recover_until.replace(tzinfo=None),
        recovered_at.replace(tzinfo=None) if recovered_at is not None else None,
        tombstone.membership_snapshot,
        tombstone.allocation_snapshot,
        tombstone.object_manifest,
    )


def test_deleted_library_recovery_rejects_foreign_and_expired_authority(
    client: TestClient,
    session: Session,
) -> None:
    owner = add_library_user(session, "a7_deleting_owner")
    viewer = add_library_user(session, "a7_deleted_viewer")
    outsider = add_library_user(session, "a7_deleted_outsider")
    library = Library(
        name="A7 recovery library",
        slug="a7-recovery-library",
        created_by_user_id=owner.id,
    )
    session.add(library)
    session.flush()
    session.add_all(
        (
            LibraryMembership(
                library_id=library.id,
                user_id=owner.id,
                role="OWNER",
                selected_reading_user_id=owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_ONLY",
                selected_reading_user_id=owner.id,
            ),
        )
    )
    session.commit()

    authenticate_library(client, session, owner)
    deleted = client.request(
        "DELETE",
        f"/api/v1/libraries/{library.id}",
        json={
            "current_password": LIBRARY_PASSWORD,
            "confirmation_name": library.name,
            "acknowledge_permanent_deletion": True,
        },
        headers=library_csrf(),
    )
    assert deleted.status_code == 200, deleted.text
    deletion_id = UUID(deleted.json()["deletion_id"])
    tombstone = session.get(LibraryDeletionTombstone, deletion_id)
    assert tombstone is not None
    baseline = _library_tombstone_snapshot(tombstone)

    for actor in (viewer, outsider):
        authenticate_library(client, session, actor)
        denied = client.post(
            f"/api/v1/account/deleted-libraries/{deletion_id}/restore",
            json={"current_password": LIBRARY_PASSWORD},
            headers={"X-CSRF-Token": LIBRARY_CSRF},
        )
        assert denied.status_code == 404
        session.refresh(tombstone)
        assert _library_tombstone_snapshot(tombstone) == baseline

    tombstone.created_at = datetime.now(UTC) - timedelta(hours=49)
    tombstone.recover_until = datetime.now(UTC) - timedelta(hours=1)
    session.commit()
    expired_baseline = _library_tombstone_snapshot(tombstone)
    authenticate_library(client, session, owner)
    expired = client.post(
        f"/api/v1/account/deleted-libraries/{deletion_id}/restore",
        json={"current_password": LIBRARY_PASSWORD},
        headers=library_csrf(),
    )
    assert expired.status_code == 410
    session.refresh(tombstone)
    assert _library_tombstone_snapshot(tombstone) == expired_baseline


def test_account_deletion_revokes_sessions_and_expired_token_cannot_avoid_cleanup(
    client: TestClient,
    session: Session,
    email_sender,
    tmp_path,
) -> None:
    user = add_account_user(session, "a7_expired_account")
    storage = FilesystemCoverStorage(tmp_path / "a7-private")
    object_key = "profile-images/a7-expired.webp"
    storage.put(object_key, b"private-profile")
    session.add(
        UserProfileImage(
            user_id=user.id,
            object_key=object_key,
            media_type="image/webp",
            byte_size=len(b"private-profile"),
            width_px=1,
            height_px=1,
            sha256="7" * 64,
        )
    )
    session.commit()

    authenticate_account(client, session, user)
    authenticate_account(client, session, user)
    assert session.query(UserSession).filter_by(user_id=user.id).count() == 2
    deleted = client.request(
        "DELETE",
        "/api/v1/account",
        json=account_delete_payload(user.username),
        headers={"X-CSRF-Token": ACCOUNT_CSRF},
    )
    assert deleted.status_code == 200, deleted.text
    sessions = session.query(UserSession).filter_by(user_id=user.id).all()
    assert len(sessions) == 2
    assert all(item.revoked_at is not None for item in sessions)
    assert client.get("/api/v1/auth/me").status_code == 401

    recovery_url = next(
        line for line in email_sender.emails[0].text.splitlines() if "?token=" in line
    )
    recovery_token = parse_qs(urlparse(recovery_url).query)["token"][0]
    tombstone = session.query(AccountDeletionTombstone).filter_by(user_id=user.id).one()
    tombstone.created_at = datetime.now(UTC) - timedelta(hours=49)
    tombstone.recover_until = datetime.now(UTC) - timedelta(hours=1)
    session.commit()

    expired = client.post(
        "/api/v1/auth/account-deletion/restore",
        json={"token": recovery_token},
    )
    assert expired.status_code == 400
    session.refresh(tombstone)
    assert tombstone.state == "PENDING"
    assert tombstone.recovery_token_consumed_at is None

    assert finalize_expired_account_deletions(
        session, storage, now=datetime.now(UTC)
    ) == 1
    assert session.get(User, user.id) is None
    finalized = session.get(AccountDeletionTombstone, tombstone.id)
    assert finalized is not None
    assert finalized.state == "FINALIZED"
    assert finalized.username is None and finalized.email is None
    assert finalized.recovery_token_hash is None
    assert finalized.membership_snapshot == []
    assert finalized.object_manifest == []
    with pytest.raises(FileNotFoundError):
        storage.read(object_key)
