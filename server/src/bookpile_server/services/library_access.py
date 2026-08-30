from dataclasses import dataclass
from uuid import UUID

from ..repositories.libraries import LibraryRepository


class LibraryNotFoundError(Exception):
    """Hide both missing libraries and libraries inaccessible to this user."""


class LibraryMapAccessDeniedError(Exception):
    pass


class LibraryOwnerRequiredError(Exception):
    pass


@dataclass(frozen=True)
class LibraryAccess:
    library_id: UUID
    user_id: UUID
    role: str
    viewer_scope: str | None
    selected_reading_user_id: UUID | None

    @property
    def can_view_map(self) -> bool:
        return self.role == "OWNER" or self.viewer_scope == "CATALOG_AND_MAP"

    @property
    def is_owner(self) -> bool:
        return self.role == "OWNER"


class LibraryAccessService:
    def __init__(self, repository: LibraryRepository) -> None:
        self._repository = repository

    def require_catalogue(self, *, library_id: UUID, user_id: UUID) -> LibraryAccess:
        membership = self._repository.find_membership(
            library_id=library_id, user_id=user_id
        )
        if membership is None:
            raise LibraryNotFoundError
        return LibraryAccess(
            library_id=membership.library_id,
            user_id=membership.user_id,
            role=membership.role,
            viewer_scope=membership.viewer_scope,
            selected_reading_user_id=membership.selected_reading_user_id,
        )

    def require_map(self, *, library_id: UUID, user_id: UUID) -> LibraryAccess:
        access = self.require_catalogue(library_id=library_id, user_id=user_id)
        if not access.can_view_map:
            raise LibraryMapAccessDeniedError
        return access

    def require_owner(self, *, library_id: UUID, user_id: UUID) -> LibraryAccess:
        access = self.require_catalogue(library_id=library_id, user_id=user_id)
        if not access.is_owner:
            raise LibraryOwnerRequiredError
        return access
