from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
from urllib.parse import urlencode
from uuid import UUID, uuid4

from ..models import AccountDeletionTombstone, LibraryMembership
from ..config import Settings
from ..email_delivery import EmailDeliveryError, EmailSender, OutgoingEmail
from ..repositories.account_deletion import AccountDeletionRepository
from ..security.passwords import verify_password


ACCOUNT_RECOVERY_LIFETIME = timedelta(hours=48)


class AccountDeletionValidationError(Exception):
    pass


class AccountDeletionReauthenticationError(Exception):
    pass


class AccountDeletionOwnershipError(Exception):
    def __init__(self, library_names: list[str]) -> None:
        self.library_names = library_names
        super().__init__(
            "Transfer Ownership or delete these libraries first: "
            + ", ".join(library_names)
        )


class AccountRecoveryUnavailableError(Exception):
    pass


@dataclass(frozen=True)
class AccountDeletionResult:
    recover_until: datetime


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


class AccountDeletionService:
    def __init__(
        self,
        repository: AccountDeletionRepository,
        email_sender: EmailSender,
        settings: Settings,
    ) -> None:
        self.repository = repository
        self.email_sender = email_sender
        self.settings = settings

    def request_deletion(
        self,
        *,
        user_id: UUID,
        current_password: str,
        confirmation_username: str,
        acknowledge_permanent_deletion: bool,
        ip_address: str | None = None,
    ) -> AccountDeletionResult:
        self.repository.lock_storage_entitlements_first()
        user = self.repository.lock_user(user_id)
        if user is None or user.state != "active":
            raise AccountRecoveryUnavailableError
        if not verify_password(user.password_hash, current_password):
            raise AccountDeletionReauthenticationError
        if confirmation_username.strip() != user.username:
            raise AccountDeletionValidationError("Type your username exactly to confirm deletion.")
        if not acknowledge_permanent_deletion:
            raise AccountDeletionValidationError("You must acknowledge the permanent deletion warning.")

        memberships = self.repository.active_memberships(user_id, lock=True)
        owned = [item.library.name for item in memberships if item.role == "OWNER"]
        if owned:
            raise AccountDeletionOwnershipError(owned)

        now = datetime.now(UTC)
        raw_recovery_token = token_urlsafe(32)
        image = self.repository.profile_image(user_id)
        tombstone = AccountDeletionTombstone(
            id=uuid4(),
            user_id=user.id,
            username=user.username,
            email=user.email,
            recovery_token_hash=sha256(raw_recovery_token.encode("utf-8")).hexdigest(),
            membership_snapshot=[
                {
                    "library_id": str(item.library_id),
                    "role": item.role,
                    "viewer_scope": item.viewer_scope,
                    "selected_reading_user_id": (
                        str(item.selected_reading_user_id)
                        if item.selected_reading_user_id else None
                    ),
                }
                for item in memberships
            ],
            object_manifest=(
                [{"object_key": image.object_key, "byte_size": image.byte_size}]
                if image else []
            ),
            created_at=now,
            recover_until=now + ACCOUNT_RECOVERY_LIFETIME,
        )
        self.repository.add_tombstone(tombstone)
        for membership in memberships:
            self.repository.delete_membership(membership)
        user.state = "pending_deletion"

        # Revoke the current request too. Cookie clearing is handled by the API.
        from ..repositories.auth import AuthRepository

        AuthRepository(self.repository.session).revoke_all_user_sessions(user.id, now)
        AuthRepository(self.repository.session).add_security_event(
            "account_deletion_requested",
            user_id=user.id,
            ip_address=ip_address,
            details={"recover_until": tombstone.recover_until.isoformat()},
        )
        recovery_query = urlencode({"token": raw_recovery_token})
        try:
            self.email_sender.send(
                OutgoingEmail(
                    recipient=user.email,
                    subject="Restore your deleted BOOKPILE account",
                    text=(
                        "We are sad to see you go. Your BOOKPILE account is now "
                        "scheduled for permanent deletion.\n\n"
                        "If you want your account back, use this secure link during "
                        "the next 48 hours:\n\n"
                        f"{self.settings.public_base_url.rstrip('/')}/restore-account?"
                        f"{recovery_query}\n\n"
                        "After 48 hours, your account and its remaining personal data "
                        "will be permanently deleted. This single-use link is the only "
                        "way to restore the account."
                    ),
                    message_key=f"account-deletion:{tombstone.id}",
                    purpose="ACCOUNT_DELETION_RECOVERY",
                    account_deletion_tombstone_id=tombstone.id,
                )
            )
        except EmailDeliveryError:
            self.repository.rollback()
            raise
        self.repository.commit_with_storage()
        return AccountDeletionResult(recover_until=tombstone.recover_until)

    def restore(self, *, raw_token: str, ip_address: str | None = None) -> UUID:
        self.repository.lock_storage_entitlements_first()
        token_hash = sha256(raw_token.encode("utf-8")).hexdigest()
        tombstone = self.repository.pending_tombstone_by_token_hash(
            token_hash, lock=True
        )
        if tombstone is None or tombstone.recovery_token_consumed_at is not None:
            raise AccountRecoveryUnavailableError
        now = datetime.now(UTC)
        if now >= utc_value(tombstone.recover_until):
            raise AccountRecoveryUnavailableError
        user = self.repository.lock_user(tombstone.user_id)
        if user is None or user.state != "pending_deletion":
            raise AccountRecoveryUnavailableError

        for snapshot in tombstone.membership_snapshot:
            library_id = UUID(str(snapshot["library_id"]))
            if self.repository.active_library(library_id) is None:
                continue
            owners = self.repository.owner_user_ids(library_id)
            if not owners:
                continue
            recorded_perspective = snapshot.get("selected_reading_user_id")
            selected_reading_user_id = (
                UUID(str(recorded_perspective))
                if recorded_perspective else None
            )
            if selected_reading_user_id not in owners:
                selected_reading_user_id = owners[0]
            self.repository.add_membership(
                LibraryMembership(
                    library_id=library_id,
                    user_id=user.id,
                    role="VIEWER",
                    viewer_scope=str(snapshot.get("viewer_scope") or "CATALOG_ONLY"),
                    selected_reading_user_id=selected_reading_user_id,
                )
            )
        user.state = "active"
        tombstone.state = "RECOVERED"
        tombstone.recovered_at = now
        tombstone.recovery_token_consumed_at = now
        tombstone.recovery_token_hash = None
        from ..repositories.auth import AuthRepository

        AuthRepository(self.repository.session).add_security_event(
            "account_recovered", user_id=user.id, ip_address=ip_address
        )
        self.repository.commit_with_storage()
        return user.id
