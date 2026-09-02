from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from secrets import token_urlsafe
import re
import unicodedata
from uuid import UUID
from urllib.parse import parse_qs, urlparse

from sqlalchemy.exc import IntegrityError

from ..models import Library, LibraryInvitation, LibraryMembership
from ..repositories.libraries import LibraryRepository
from ..security.passwords import verify_password
from .library_access import (
    LibraryAccessService,
    LibraryNotFoundError,
)


LIBRARY_INVITATION_LIFETIME = timedelta(days=7)


class LibraryValidationError(Exception):
    pass


class LibraryConflictError(Exception):
    pass


class InvalidLibraryInvitationError(Exception):
    pass


class LibraryReauthenticationError(Exception):
    pass


class FinalOwnerError(Exception):
    pass


def hash_library_invitation_token(token: str) -> str:
    return sha256(token.encode("utf-8")).hexdigest()


def library_invitation_token(value: str) -> str:
    """Accept either the one-time secret itself or BOOKPILE's shared URL."""

    candidate = value.strip()
    if "://" in candidate:
        values = parse_qs(urlparse(candidate).query).get("library-invite", [])
        candidate = values[0].strip() if values else ""
    if len(candidate) < 32 or len(candidate) > 200:
        raise InvalidLibraryInvitationError
    return candidate


def utc_value(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def slug_base(name: str) -> str:
    normalized = unicodedata.normalize("NFKD", name)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")
    return (slug or "library")[:70].rstrip("-")


@dataclass(frozen=True)
class CreatedLibraryInvitation:
    invitation_id: UUID
    raw_token: str
    expires_at: datetime


class LibraryService:
    def __init__(self, repository: LibraryRepository) -> None:
        self._repository = repository
        self._access = LibraryAccessService(repository)

    def list_for_user(self, user_id: UUID) -> list[LibraryMembership]:
        return self._repository.list_memberships_for_user(user_id)

    def create(self, *, user_id: UUID, name: str) -> LibraryMembership:
        clean_name = " ".join(name.split())
        if not clean_name or len(clean_name) > 160:
            raise LibraryValidationError("Library name must contain 1–160 characters.")

        base = slug_base(clean_name)
        slug = base
        if self._repository.slug_exists(slug):
            slug = f"{base}-{token_urlsafe(5).lower().replace('_', 'x').replace('-', 'x')}"

        library = Library(
            name=clean_name,
            slug=slug,
            created_by_user_id=user_id,
        )
        membership = LibraryMembership(
            library=library,
            user_id=user_id,
            role="OWNER",
            selected_reading_user_id=user_id,
        )
        self._repository.add_library(library)
        self._repository.add_membership(membership)
        try:
            self._repository.flush()
        except IntegrityError as exc:
            self._repository.rollback()
            raise LibraryConflictError("Library could not be created.") from exc
        self._repository.add_audit_event(
            library_id=library.id,
            actor_user_id=user_id,
            event_type="library_created",
            details={"name": library.name},
        )
        self._repository.commit()
        return membership

    def list_members(self, *, library_id: UUID, actor_user_id: UUID) -> list[LibraryMembership]:
        self._access.require_owner(
            library_id=library_id, user_id=actor_user_id
        )
        memberships = self._repository.list_members_for_library(library_id)
        return sorted(
            memberships,
            key=lambda item: (
                item.role != "OWNER",
                item.created_at,
                str(item.id),
            ),
        )

    def list_member_summaries(
        self, *, library_id: UUID, actor_user_id: UUID
    ) -> list[LibraryMembership]:
        self._access.require_catalogue(
            library_id=library_id, user_id=actor_user_id
        )
        memberships = self._repository.list_members_for_library(library_id)
        return sorted(
            memberships,
            key=lambda item: (
                item.role != "OWNER",
                item.created_at,
                str(item.id),
            ),
        )

    def create_invitation(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        role: str,
        viewer_scope: str | None,
        acknowledge_equal_owner_power: bool,
    ) -> CreatedLibraryInvitation:
        self._access.require_owner(
            library_id=library_id, user_id=actor_user_id
        )
        role, viewer_scope = self._validated_role_scope(role, viewer_scope)
        if role == "OWNER" and not acknowledge_equal_owner_power:
            raise LibraryValidationError(
                "Equal co-Ownership authority must be acknowledged."
            )
        now = datetime.now(UTC)
        raw_token = token_urlsafe(32)
        invitation = LibraryInvitation(
            library_id=library_id,
            token_hash=hash_library_invitation_token(raw_token),
            role=role,
            viewer_scope=viewer_scope,
            created_by_user_id=actor_user_id,
            created_at=now,
            expires_at=now + LIBRARY_INVITATION_LIFETIME,
        )
        self._repository.add_invitation(invitation)
        self._repository.flush()
        self._repository.add_audit_event(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="library_invitation_created",
            details={
                "invitation_id": str(invitation.id),
                "role": role,
                "viewer_scope": viewer_scope,
            },
        )
        self._repository.commit()
        return CreatedLibraryInvitation(
            invitation_id=invitation.id,
            raw_token=raw_token,
            expires_at=invitation.expires_at,
        )

    def accept_invitation(
        self, *, raw_token: str, user_id: UUID
    ) -> LibraryMembership:
        now = datetime.now(UTC)
        raw_token = library_invitation_token(raw_token)
        invitation = self._repository.find_invitation_for_update(
            hash_library_invitation_token(raw_token)
        )
        if (
            invitation is None
            or invitation.revoked_at is not None
            or invitation.consumed_at is not None
            or now >= utc_value(invitation.expires_at)
        ):
            raise InvalidLibraryInvitationError
        assert invitation is not None
        if invitation.library.state != "active":
            raise InvalidLibraryInvitationError
        if self._repository.find_membership(
            library_id=invitation.library_id, user_id=user_id
        ) is not None:
            raise LibraryConflictError("User is already a member of this library.")

        selected_user_id = user_id if invitation.role == "OWNER" else None
        if invitation.role == "VIEWER":
            owners = [
                member
                for member in self._repository.list_members_for_library(
                    invitation.library_id
                )
                if member.role == "OWNER"
            ]
            if not owners:
                raise InvalidLibraryInvitationError
            selected_user_id = owners[0].user_id

        membership = LibraryMembership(
            library=invitation.library,
            user_id=user_id,
            role=invitation.role,
            viewer_scope=invitation.viewer_scope,
            selected_reading_user_id=selected_user_id,
        )
        self._repository.add_membership(membership)
        invitation.consumed_by_user_id = user_id
        invitation.consumed_at = now
        try:
            self._repository.flush()
        except IntegrityError as exc:
            self._repository.rollback()
            raise LibraryConflictError("Invitation could not be accepted.") from exc
        self._repository.add_audit_event(
            library_id=invitation.library_id,
            actor_user_id=user_id,
            event_type="library_invitation_accepted",
            details={
                "invitation_id": str(invitation.id),
                "role": invitation.role,
            },
        )
        self._repository.commit()
        return membership

    def revoke_invitation(
        self, *, library_id: UUID, invitation_id: UUID, actor_user_id: UUID
    ) -> None:
        self._access.require_owner(
            library_id=library_id, user_id=actor_user_id
        )
        invitation = self._repository.find_invitation(invitation_id)
        if (
            invitation is None
            or invitation.library_id != library_id
            or invitation.consumed_at is not None
            or invitation.revoked_at is not None
        ):
            raise LibraryNotFoundError
        invitation.revoked_at = datetime.now(UTC)
        self._repository.add_audit_event(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="library_invitation_revoked",
            details={"invitation_id": str(invitation.id)},
        )
        self._repository.commit()

    def change_member(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        target_user_id: UUID,
        action: str,
        viewer_scope: str | None,
        current_password: str,
        acknowledge_equal_owner_power: bool,
    ) -> LibraryMembership | None:
        self._access.require_owner(
            library_id=library_id, user_id=actor_user_id
        )
        actor = self._repository.find_user(actor_user_id)
        if actor is None or not verify_password(actor.password_hash, current_password):
            raise LibraryReauthenticationError

        members = self._repository.lock_members_for_library(library_id)
        actor_membership = next(
            (item for item in members if item.user_id == actor_user_id), None
        )
        target = next((item for item in members if item.user_id == target_user_id), None)
        if actor_membership is None or actor_membership.role != "OWNER" or target is None:
            raise LibraryNotFoundError

        normalized_action = action.strip().upper()
        previous_role = target.role
        previous_scope = target.viewer_scope

        if normalized_action == "CHANGE_VIEWER_SCOPE":
            if target.role != "VIEWER":
                raise LibraryValidationError("Target member is not a Viewer.")
            _, scope = self._validated_role_scope("VIEWER", viewer_scope)
            target.viewer_scope = scope
        elif normalized_action == "PROMOTE_TO_OWNER":
            if target.role != "VIEWER":
                raise LibraryValidationError("Target member is not a Viewer.")
            if not acknowledge_equal_owner_power:
                raise LibraryValidationError(
                    "Equal co-Ownership authority must be acknowledged."
                )
            target.role = "OWNER"
            target.viewer_scope = None
            target.selected_reading_user_id = target.user_id
        elif normalized_action in {"DOWNGRADE_TO_VIEWER", "REMOVE"}:
            if target.role == "OWNER":
                remaining_owners = [
                    item
                    for item in members
                    if item.role == "OWNER" and item.user_id != target.user_id
                ]
                if not remaining_owners:
                    raise FinalOwnerError
                replacement_perspective = remaining_owners[0].user_id
                for member in members:
                    if member.selected_reading_user_id == target.user_id:
                        member.selected_reading_user_id = replacement_perspective
                self._repository.revoke_open_invitations_by_creator(
                    library_id=library_id,
                    creator_user_id=target.user_id,
                    now=datetime.now(UTC),
                )
            if normalized_action == "DOWNGRADE_TO_VIEWER":
                _, scope = self._validated_role_scope("VIEWER", viewer_scope)
                target.role = "VIEWER"
                target.viewer_scope = scope
            else:
                self._repository.delete_membership(target)
        else:
            raise LibraryValidationError("Invalid membership action.")

        self._repository.add_audit_event(
            library_id=library_id,
            actor_user_id=actor_user_id,
            event_type="library_membership_changed",
            details={
                "target_user_id": str(target_user_id),
                "action": normalized_action,
                "previous_role": previous_role,
                "previous_scope": previous_scope,
                "new_role": None if normalized_action == "REMOVE" else target.role,
                "new_scope": (
                    None if normalized_action == "REMOVE" else target.viewer_scope
                ),
            },
        )
        self._repository.commit()
        return None if normalized_action == "REMOVE" else target

    def list_reading_perspectives(
        self, *, library_id: UUID, actor_user_id: UUID
    ) -> tuple[LibraryMembership, list[LibraryMembership]]:
        access = self._access.require_catalogue(
            library_id=library_id, user_id=actor_user_id
        )
        actor_membership = self._repository.find_membership(
            library_id=library_id, user_id=actor_user_id
        )
        assert actor_membership is not None
        owners = [
            item
            for item in self._repository.list_members_for_library(library_id)
            if item.role == "OWNER"
        ]
        if not owners:
            raise LibraryNotFoundError
        if access.selected_reading_user_id not in {item.user_id for item in owners}:
            actor_membership.selected_reading_user_id = owners[0].user_id
            self._repository.commit()
        return actor_membership, owners

    def select_reading_perspective(
        self, *, library_id: UUID, actor_user_id: UUID, selected_user_id: UUID
    ) -> LibraryMembership:
        actor_membership, owners = self.list_reading_perspectives(
            library_id=library_id, actor_user_id=actor_user_id
        )
        if selected_user_id not in {item.user_id for item in owners}:
            raise LibraryValidationError(
                "Reading perspective must be an Owner of this library."
            )
        actor_membership.selected_reading_user_id = selected_user_id
        self._repository.commit()
        return actor_membership

    @staticmethod
    def _validated_role_scope(
        role: str, viewer_scope: str | None
    ) -> tuple[str, str | None]:
        normalized_role = role.strip().upper()
        normalized_scope = viewer_scope.strip().upper() if viewer_scope else None
        if normalized_role == "OWNER" and normalized_scope is None:
            return normalized_role, None
        if normalized_role == "VIEWER" and normalized_scope in {
            "CATALOG_ONLY",
            "CATALOG_AND_MAP",
        }:
            return normalized_role, normalized_scope
        raise LibraryValidationError("Invalid library role or Viewer scope.")
