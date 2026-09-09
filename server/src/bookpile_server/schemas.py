from datetime import date, datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    field_validator,
    model_validator,
)

from .isbn import InvalidISBN, normalize_isbn


TranslationStatus = Literal["UNKNOWN", "ORIGINAL", "TRANSLATED"]
FictionCategory = Literal["FICTION", "NON_FICTION"]
Binding = Literal["HARDCOVER", "PAPERBACK", "FLEXIBOUND", "SPIRAL", "STAPLED", "OTHER"]
PublicationType = Literal[
    "CONVENTIONAL_BOOK",
    "COMIC_GRAPHIC_NOVEL",
    "ATLAS",
    "REFERENCE",
    "ART_PHOTOGRAPHY_ILLUSTRATED",
    "MAGAZINE_PERIODICAL",
    "OTHER",
]
ProfileVisibility = Literal["PRIVATE", "SHARED_LIBRARY_MEMBERS", "AUTHENTICATED"]
ProfileGender = Literal["UNSPECIFIED", "MALE", "FEMALE", "CUSTOM"]
ProfilePronoun = Literal["MALE", "FEMALE", "NEUTRAL"]


class LocalImportWarningResponse(BaseModel):
    code: str
    message: str | None = None
    count: int | None = None


class LocalImportPreflightResponse(BaseModel):
    import_id: UUID
    library_id: UUID
    state: Literal["READY"]
    adapter: str
    backup_format_version: int
    local_schema_version: int
    source_created_at: str
    reading_owner_user_id: UUID | None
    counts: dict[str, int]
    estimated_logical_bytes: int
    capacity_available: bool
    expires_at: datetime
    warnings: list[LocalImportWarningResponse]


class LocalImportJobResponse(LocalImportPreflightResponse):
    state: Literal["READY", "IMPORTING", "IMPORTED", "FAILED", "EXPIRED"]
    result_counts: dict[str, int] | None = None


class ConsolidateLocalImportRequest(BaseModel):
    allow_repeated_archive: bool = False


class ConsolidateLocalImportAsNewLibraryRequest(ConsolidateLocalImportRequest):
    name: str = Field(min_length=1, max_length=160)


def optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = " ".join(value.split())
    return cleaned or None


def normalize_genres(value: str | None) -> str | None:
    if value is None:
        return None
    genres: dict[str, str] = {}
    for part in re.split(r"[,;\r\n]+", value):
        cleaned = " ".join(part.split())
        if cleaned:
            genres.setdefault(cleaned.casefold(), cleaned)
    return ", ".join(sorted(genres.values(), key=str.casefold)) or None


class ProfileWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, max_length=100)
    timezone: str | None = Field(default=None, max_length=64)
    gender: ProfileGender = "UNSPECIFIED"
    custom_gender: str | None = Field(default=None, max_length=80)
    preferred_pronoun: ProfilePronoun | None = None
    neutral_pronoun: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    state: str | None = Field(default=None, max_length=120)
    country: str | None = Field(default=None, max_length=120)
    date_of_birth: date | None = None
    visibilities: dict[
        Literal[
            "display_name", "timezone", "personal_data", "profile_image"
        ],
        ProfileVisibility,
    ] = Field(default_factory=dict)

    @field_validator(
        "display_name", "timezone", "custom_gender", "neutral_pronoun",
        "city", "state", "country",
    )
    @classmethod
    def normalize_profile_text(cls, value: str | None) -> str | None:
        return optional_text(value)

    @model_validator(mode="after")
    def validate_gender_shape(self) -> "ProfileWrite":
        if self.gender != "CUSTOM":
            # Older clients may echo a derived MALE/FEMALE pronoun from a
            # profile response. Non-Custom gender has no separate pronoun
            # controls, so normalise those stale details instead of rejecting
            # an otherwise valid profile save.
            self.custom_gender = None
            self.preferred_pronoun = None
            self.neutral_pronoun = None
            return self
        if not self.custom_gender:
            raise ValueError("Custom gender is required")
        if self.preferred_pronoun is None:
            raise ValueError("Preferred pronoun is required for Custom gender")
        if self.preferred_pronoun != "NEUTRAL" and self.neutral_pronoun:
            raise ValueError("Custom pronoun text is available only for Neutral pronouns")
        return self


class ProfileResponse(BaseModel):
    user_id: UUID
    username: str
    display_name: str | None = None
    timezone: str | None = None
    gender: ProfileGender | None = None
    custom_gender: str | None = None
    preferred_pronoun: ProfilePronoun | None = None
    neutral_pronoun: str | None = None
    city: str | None = None
    state: str | None = None
    country: str | None = None
    date_of_birth: date | None = None
    profile_image_visible: bool = False
    visibilities: dict[str, ProfileVisibility] | None = None


class StorageLibraryContributionResponse(BaseModel):
    library_id: UUID
    name: str
    colour_key: int = Field(ge=0)
    share_of_used: float = Field(ge=0, le=1)
    share_of_entitlement: float = Field(ge=0, le=1)


class StorageOverviewResponse(BaseModel):
    libraries: list[StorageLibraryContributionResponse]
    account_data_share_of_used: float = Field(ge=0, le=1)
    account_data_share_of_entitlement: float = Field(ge=0, le=1)
    used_share_of_entitlement: float = Field(ge=0, le=1)


class PrivateAccountResponse(BaseModel):
    user_id: UUID
    username: str
    email: str
    created_at: datetime
    password_protected: bool = True


class BetaInvitationStatusResponse(BaseModel):
    active_day_count: int = Field(ge=0, le=2)
    days_required: int = 3
    available_credits: int = Field(ge=0)
    open_invitations: int = Field(ge=0)


class EarnedAccountInvitationResponse(BaseModel):
    invitation_id: UUID
    invitation_token: str
    expires_at: datetime


class ChangePasswordWrite(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)
    confirmation: str = Field(min_length=12, max_length=128)


class DeleteAccountWrite(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    confirmation_username: str = Field(min_length=1, max_length=30)
    acknowledge_permanent_deletion: bool = False


class AccountDeletionResponse(BaseModel):
    recover_until: datetime


class RestoreAccountWrite(BaseModel):
    token: str = Field(min_length=32, max_length=256)


class ContributorWrite(BaseModel):
    role_code: str = Field(min_length=1, max_length=40)
    name: str = Field(min_length=1, max_length=300)

    @field_validator("role_code")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        cleaned = value.strip().upper()
        if not cleaned:
            raise ValueError("Contributor role is required")
        return cleaned

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Contributor name is required")
        return cleaned


class ContributorResponse(ContributorWrite):
    id: UUID
    position: int
    role_label: str


class ContributorRoleResponse(BaseModel):
    code: str
    label: str
    sort_order: int


class CoverMetadataResponse(BaseModel):
    width_px: int
    height_px: int
    byte_size: int
    updated_at: datetime


class BookcaseWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=500)
    height_mm: int | None = Field(default=None, gt=0, le=100000)
    width_mm: int | None = Field(default=None, gt=0, le=100000)
    depth_mm: int | None = Field(default=None, gt=0, le=100000)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Bookcase name is required")
        return cleaned

    @field_validator("description")
    @classmethod
    def normalize_description(cls, value: str | None) -> str | None:
        return optional_text(value)


class BookcaseCreate(BookcaseWrite):
    shelf_direction: Literal[
        "TOP_TO_BOTTOM", "BOTTOM_TO_TOP", "LEFT_TO_RIGHT", "RIGHT_TO_LEFT"
    ] = "TOP_TO_BOTTOM"
    homogeneous_structure: bool = True


class ShelfWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    bookcase_id: UUID
    shelf_number: int = Field(gt=0)
    usable_height_mm: int | None = Field(default=None, gt=0, le=100000)
    usable_width_mm: int | None = Field(default=None, gt=0, le=100000)
    usable_depth_mm: int | None = Field(default=None, gt=0, le=100000)


class ShelfUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shelf_number: int = Field(gt=0)
    usable_height_mm: int | None = Field(default=None, gt=0, le=100000)
    usable_width_mm: int | None = Field(default=None, gt=0, le=100000)
    usable_depth_mm: int | None = Field(default=None, gt=0, le=100000)


class ContainerWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    shelf_id: UUID
    container_type: Literal["ROW", "PILE"]
    layer: Literal["BACKGROUND", "FOREGROUND"]
    container_number: int = Field(gt=0)


class ContainerUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container_number: int = Field(gt=0)


class PhysicalDeleteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmed: Literal[True]


class BookPlacementWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container_id: UUID | None = None
    position: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_pair(self) -> "BookPlacementWrite":
        if (self.container_id is None) != (self.position is None):
            raise ValueError("Container and position must be provided together")
        return self


class RearrangementStepWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    container_id: UUID
    position: int = Field(gt=0)
    new_position_mode: Literal["SQUEEZE", "SWAP", "CONTINUE"] = "SQUEEZE"


class RearrangementOperationWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    book_id: UUID
    old_position_mode: Literal["COLLAPSE", "LEAVE_GAP"] = "COLLAPSE"
    release_shelf_space: bool = False
    steps: list[RearrangementStepWrite] = Field(default_factory=list, max_length=100)


class RearrangementRequest(RearrangementOperationWrite):
    completed_operations: list[RearrangementOperationWrite] = Field(
        default_factory=list, max_length=100
    )


class RearrangementApplyRequest(RearrangementRequest):
    revision: str = Field(min_length=64, max_length=64)


class RearrangementPlacementResponse(BaseModel):
    book_id: UUID
    container_id: UUID | None
    position: int | None


class RearrangementGapResponse(BaseModel):
    container_id: UUID
    positions: list[int]


class PhysicalBookResponse(BaseModel):
    id: UUID
    title: str
    author: str
    page_count: int | None
    publisher: str | None
    current_ed_year: int | None
    original_publication_year: int | None
    language: str | None
    original_language: str | None
    translation_status: str
    fiction_category: str | None
    binding: str | None
    publication_type: str | None
    genre_text: str | None
    acquisition_date: date | None
    is_original_collection: bool
    height_mm: int | None
    width_mm: int | None
    thickness_mm: int | None
    container_id: UUID | None
    position: int | None


class VisualBookcaseLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    bookcase_id: UUID
    x_mm: float
    floor_y_mm: float
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    shelf_direction: Literal["TOP_TO_BOTTOM", "BOTTOM_TO_TOP", "LEFT_TO_RIGHT", "RIGHT_TO_LEFT"] = "TOP_TO_BOTTOM"
    homogeneous_structure: bool = True
    frame_left_mm: float = Field(ge=0)
    frame_right_mm: float = Field(ge=0)
    top_closure_mm: float = Field(ge=0)
    bottom_closure_mm: float = Field(ge=0)
    separator_thickness_mm: float = Field(ge=5)


class VisualShelfLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    shelf_id: UUID
    height_weight: float = Field(gt=0)
    x_mm: float
    floor_y_mm: float
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)
    alignment: Literal["LEFT", "CENTER", "RIGHT"] = "CENTER"
    offset_mm: float = 0
    width_source: Literal["ENTERED", "FALLBACK", "DERIVED"] = "DERIVED"
    height_source: Literal["ENTERED", "FALLBACK", "DERIVED"] = "DERIVED"
    open_top: bool = False
    left_frame_mm: float = Field(ge=0)
    right_frame_mm: float = Field(ge=0)
    top_closure_mm: float = Field(ge=0)
    bottom_board_mm: float = Field(ge=0)
    separator_after_mm: float | None = Field(default=None, ge=5)
    separator_anchor: Literal["TOP", "BOTTOM"] = "BOTTOM"
    separator_height_mm: float | None = Field(default=None, ge=5)
    separator_source: Literal["ENTERED", "FALLBACK", "DERIVED"] | None = None


class VisualContainerLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    container_id: UUID
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)
    row_anchor: Literal["LEFT", "RIGHT"] = "LEFT"
    support_kind: Literal["SHELF", "CONTAINER"] = "SHELF"
    support_container_id: UUID | None = None
    pile_alignment: Literal["LEFT", "CENTER", "RIGHT"] = "RIGHT"

class RearrangementResultResponse(BaseModel):
    revision: str
    valid_to_apply: bool
    complete: bool
    effective_old_position_mode: Literal["COLLAPSE", "LEAVE_GAP"]
    next_active_book_id: UUID | None = None
    placements: list[RearrangementPlacementResponse]
    gaps: list[RearrangementGapResponse]
    movement_log: list[str]
    movement_groups: list[list[str]]
    warnings: list[str]
    geometry_errors: list[str]
    container_layouts: list[VisualContainerLayoutWrite]


class VisualOutsideAreaWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    area_kind: Literal["READING", "LOANED"]
    x_mm: float
    y_mm: float
    width_mm: float = Field(gt=0)
    height_mm: float = Field(gt=0)


class VisualLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str = Field(min_length=64, max_length=64)
    geometry_mode: Literal["MANUAL", "PHYSICAL"]
    coordinate_system_version: Literal[2]
    refresh_shelves_from_physical: bool = False
    bookcases: list[VisualBookcaseLayoutWrite]
    shelves: list[VisualShelfLayoutWrite]
    containers: list[VisualContainerLayoutWrite]
    outside_areas: list[VisualOutsideAreaWrite]
    diagnostics: list["GeometryDiagnosticResponse"] = Field(default_factory=list)


class VisualLayoutResponse(BaseModel):
    revision: str
    geometry_mode: Literal["MANUAL", "PHYSICAL"]
    coordinate_system_version: int
    bookcases: list[VisualBookcaseLayoutWrite]
    shelves: list[VisualShelfLayoutWrite]
    containers: list[VisualContainerLayoutWrite]
    outside_areas: list[VisualOutsideAreaWrite]
    diagnostics: list["GeometryDiagnosticResponse"] = Field(default_factory=list)


class GeometryDiagnosticResponse(BaseModel):
    entity_kind: Literal["LIBRARY", "BOOKCASE", "SHELF", "CONTAINER", "BOOK"]
    entity_id: UUID | None
    severity: Literal["INFO", "WARNING", "ERROR"]
    code: str
    message: str


class ContainerResponse(BaseModel):
    id: UUID
    shelf_id: UUID
    container_type: Literal["ROW", "PILE"]
    layer: Literal["BACKGROUND", "FOREGROUND"]
    container_number: int
    book_count: int
    created_at: datetime
    updated_at: datetime


class ShelfResponse(BaseModel):
    id: UUID
    bookcase_id: UUID
    shelf_number: int
    usable_height_mm: int | None
    usable_width_mm: int | None
    usable_depth_mm: int | None
    book_count: int
    containers: list[ContainerResponse]
    created_at: datetime
    updated_at: datetime


class BookcaseResponse(BaseModel):
    id: UUID
    name: str
    description: str | None
    height_mm: int | None
    width_mm: int | None
    depth_mm: int | None
    book_count: int
    shelves: list[ShelfResponse]
    created_at: datetime
    updated_at: datetime


class PhysicalLibraryResponse(BaseModel):
    library_id: UUID
    role: Literal["OWNER", "VIEWER"]
    can_edit: bool
    bookcases: list[BookcaseResponse]
    books: list[PhysicalBookResponse]
    layout: VisualLayoutResponse


class BookWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=500)
    author: str = Field(min_length=1, max_length=500)
    isbn_10: str | None = Field(default=None, max_length=40)
    isbn_13: str | None = Field(default=None, max_length=40)
    subtitle: str | None = Field(default=None, max_length=500)
    page_count: int | None = Field(default=None, gt=0)
    publisher: str | None = Field(default=None, max_length=300)
    current_ed_year: int | None = Field(default=None, ge=1000, le=9999)
    original_publication_year: int | None = Field(default=None, ge=1000, le=9999)
    language: str | None = Field(default=None, max_length=200)
    original_language: str | None = Field(default=None, max_length=200)
    translation_status: TranslationStatus = "UNKNOWN"
    edition_number: int | None = Field(default=None, gt=0)
    fiction_category: FictionCategory | None = None
    binding: Binding | None = None
    publication_type: PublicationType | None = None
    genre_text: str | None = Field(default=None, max_length=1000)
    series_name: str | None = Field(default=None, max_length=300)
    series_volume: str | None = Field(default=None, max_length=100)
    notes: str | None = Field(default=None, max_length=4000)
    acquisition_date: date | None = None
    is_original_collection: bool = False
    height_mm: int | None = Field(default=None, gt=0, le=10000)
    width_mm: int | None = Field(default=None, gt=0, le=10000)
    thickness_mm: int | None = Field(default=None, gt=0, le=10000)
    contributors: list[ContributorWrite] = Field(default_factory=list, max_length=250)

    @field_validator("title", "author")
    @classmethod
    def normalize_required(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Title and author are required")
        return cleaned

    @field_validator(
        "subtitle",
        "publisher",
        "language",
        "original_language",
        "series_name",
        "series_volume",
        "notes",
    )
    @classmethod
    def normalize_optional(cls, value: str | None) -> str | None:
        return optional_text(value)

    @field_validator("genre_text")
    @classmethod
    def normalize_genre_text(cls, value: str | None) -> str | None:
        return normalize_genres(value)

    @field_validator("isbn_10")
    @classmethod
    def normalize_isbn_10(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        try:
            normalized = normalize_isbn(value)
        except InvalidISBN as exc:
            raise ValueError(str(exc)) from exc
        if len(normalized) != 10:
            raise ValueError("ISBN-10 must be entered in the ISBN-10 field")
        return normalized

    @field_validator("isbn_13")
    @classmethod
    def normalize_isbn_13(cls, value: str | None) -> str | None:
        if not value or not value.strip():
            return None
        try:
            normalized = normalize_isbn(value)
        except InvalidISBN as exc:
            raise ValueError(str(exc)) from exc
        if len(normalized) != 13:
            raise ValueError("ISBN-13 must be entered in the ISBN-13 field")
        return normalized

    @model_validator(mode="after")
    def validate_structure(self) -> "BookWrite":
        seen: set[tuple[str, str]] = set()
        authors = 0
        for contributor in self.contributors:
            key = (contributor.role_code, contributor.name.casefold())
            if key in seen:
                raise ValueError("The same contributor cannot have the same role twice")
            seen.add(key)
            if contributor.role_code == "AUTHOR":
                authors += 1
        if authors >= 2 and self.author != "Multiple authors":
            raise ValueError("Two or more structured authors require author = Multiple authors")
        if authors < 2 and self.author == "Multiple authors":
            raise ValueError("Multiple authors requires at least two AUTHOR contributors")
        if self.translation_status == "TRANSLATED":
            if not self.language or not self.original_language:
                raise ValueError("Translated books require current and original languages")
            if self.language.casefold() == self.original_language.casefold():
                raise ValueError("Translated books require two different languages")
        return self


class BookWithPlacementWrite(BaseModel):
    """One atomic catalogue-and-physical-copy write."""

    model_config = ConfigDict(extra="forbid")

    book: BookWrite
    placement: BookPlacementWrite


class InitialLoanWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loaned_to: str = Field(min_length=1, max_length=300)
    notes: str | None = Field(default=None, max_length=4000)
    loaned_date: date | None = None
    expected_return_date: date | None = None


class BookWithPlacementAndLoanWrite(BookWithPlacementWrite):
    loan: InitialLoanWrite


class BookSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    author: str
    display_author: str
    subtitle: str | None
    page_count: int | None
    publisher: str | None
    current_ed_year: int | None
    language: str | None
    fiction_category: str | None
    binding: str | None
    publication_type: str | None
    genre_text: str | None
    series_name: str | None
    series_volume: str | None
    contributors: list[ContributorResponse]
    cover: CoverMetadataResponse | None = None
    created_at: datetime
    updated_at: datetime


class BookResponse(BookSummary):
    library_id: UUID
    isbn_10: str | None
    isbn_13: str | None
    original_publication_year: int | None
    original_language: str | None
    translation_status: str
    edition_number: int | None
    notes: str | None
    acquisition_date: date | None
    is_original_collection: bool
    height_mm: int | None
    width_mm: int | None
    thickness_mm: int | None


class DeleteBookRequest(BaseModel):
    confirmation_title: str = Field(min_length=1, max_length=500)


class CatalogueMetadataOptions(BaseModel):
    languages: list[str]
    original_languages: list[str]
    publishers: list[str]
    genres: list[str]
    series_names: list[str]
    contributor_roles: list[ContributorRoleResponse]


class CatalogueResponse(BaseModel):
    library_id: UUID
    role: str
    can_edit: bool
    total: int
    limit: int
    offset: int
    books: list[BookSummary]


class LoginRequest(BaseModel):
    identifier: str = Field(min_length=1, max_length=320)
    password: str = Field(min_length=1, max_length=128)
    remember_me: bool = False


class LoginResponse(BaseModel):
    user_id: UUID
    username: str
    expires_at: datetime
    absolute_expires_at: datetime


class CurrentUserResponse(BaseModel):
    user_id: UUID
    username: str


class RegisterAccountRequest(BaseModel):
    invitation_token: str = Field(min_length=32, max_length=200)
    email: str = Field(min_length=3, max_length=320)
    username: str = Field(min_length=1, max_length=30)
    password: str = Field(min_length=1, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)


class RegisterAccountResponse(BaseModel):
    user_id: UUID
    username: str
    state: str
    verification_email_sent: bool


class EmailAddressRequest(BaseModel):
    email: str = Field(min_length=3, max_length=320)


class AccountTokenRequest(BaseModel):
    token: str = Field(min_length=32, max_length=200)


class PasswordResetConfirmRequest(AccountTokenRequest):
    password: str = Field(min_length=1, max_length=128)
    password_confirmation: str = Field(min_length=1, max_length=128)


class CreateLibraryRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160)


class LibrarySummaryResponse(BaseModel):
    library_id: UUID
    name: str
    slug: str
    role: str
    viewer_scope: str | None
    selected_reading_user_id: UUID | None
    can_view_map: bool


class LibraryMemberResponse(BaseModel):
    user_id: UUID
    username: str
    role: str
    viewer_scope: str | None
    selected_reading_user_id: UUID | None
    created_at: datetime


class LibraryMemberSummaryResponse(BaseModel):
    user_id: UUID
    username: str
    role: str
    viewer_scope: str | None


class CreateLibraryInvitationRequest(BaseModel):
    role: str = Field(min_length=1, max_length=16)
    viewer_scope: str | None = Field(default=None, max_length=32)
    acknowledge_equal_owner_power: bool = False


class CreatedLibraryInvitationResponse(BaseModel):
    invitation_id: UUID
    invitation_token: str
    expires_at: datetime


class AcceptLibraryInvitationRequest(BaseModel):
    invitation_token: str = Field(min_length=32, max_length=200)


class ChangeLibraryMemberRequest(BaseModel):
    action: str = Field(min_length=1, max_length=32)
    viewer_scope: str | None = Field(default=None, max_length=32)
    current_password: str = Field(min_length=1, max_length=128)
    acknowledge_equal_owner_power: bool = False


class ReadingPerspectiveResponse(BaseModel):
    user_id: UUID
    username: str
    selected: bool
    writable: bool


class SelectReadingPerspectiveRequest(BaseModel):
    user_id: UUID


class DeleteLibraryRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    confirmation_name: str = Field(min_length=1, max_length=160)
    acknowledge_permanent_deletion: bool = False


class RestoreLibraryRequest(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)


class RecoverableLibraryResponse(BaseModel):
    deletion_id: UUID
    library_id: UUID
    name: str
    deleted_at: datetime
    recover_until: datetime


class ReadingSessionResponse(BaseModel):
    id: UUID
    state: str
    started_date: date | None
    finished_date: date | None
    dates_unknown: bool
    created_at: datetime
    updated_at: datetime


class BookReadingResponse(BaseModel):
    library_id: UUID
    book_id: UUID
    perspective_user_id: UUID
    state: str
    active_reader_present: bool
    writable: bool
    total_sessions: int
    limit: int
    offset: int
    sessions: list[ReadingSessionResponse]


class StartReadingRequest(BaseModel):
    started_date: date


class FinishReadingRequest(BaseModel):
    finished_date: date


class HistoricalReadingWrite(BaseModel):
    started_date: date | None = None
    finished_date: date | None = None
    dates_unknown: bool = False


class GoodreadsWrite(BaseModel):
    url: str | None = Field(default=None, max_length=2048)


class GoodreadsReviewResponse(BaseModel):
    user_id: UUID
    username: str
    url: str


class ReadingCatalogueItemResponse(BaseModel):
    book_id: UUID
    state: str
    active_reader_present: bool
    goodreads_url: str | None
    started_date: date | None
    finished_date: date | None
    dates_unknown: bool


class ReadingCatalogueOverviewResponse(BaseModel):
    perspective_user_id: UUID
    writable: bool
    pending: int
    reading: int
    rereading: int
    read: int
    active_display: str
    items: list[ReadingCatalogueItemResponse]


class ReadingStatisticsBookResponse(BaseModel):
    book_id: UUID
    title: str
    author: str
    reading_events: int
    pages_read: int
    average_pages_per_day: float | None
    latest_finished_date: date | None


class ReadingDurationStatisticResponse(BaseModel):
    average_days: float | None
    median_days: float | None
    sample_size: int
    excluded: int


class ReadingStatisticsYearResponse(BaseModel):
    year: int
    reading_events: int
    books_read: int
    pages_read: int


class ReadingStatisticsResponse(BaseModel):
    perspective_user_id: UUID
    total_catalogue_books: int
    unique_books_read: int
    completed_readings: int
    dated_readings: int
    rereadings: int
    pages_read: int
    average_pages_per_day: float | None
    median_pages_per_day: float | None
    pages_per_week: float | None
    pages_per_month: float | None
    active_readings: int
    pending_duration: ReadingDurationStatisticResponse
    reading_duration: ReadingDurationStatisticResponse
    books: list[ReadingStatisticsBookResponse]
    years: list[ReadingStatisticsYearResponse]


class ActiveLoanWrite(InitialLoanWrite):
    pass


class ReturnLoanWrite(BaseModel):
    returned_date: date | None = None


class HistoricalLoanWrite(ActiveLoanWrite):
    returned_date: date | None = None


class ViewerLoanResponse(BaseModel):
    id: UUID
    book_id: UUID
    state: Literal["ACTIVE", "RETURNED"]
    loaned_date: date | None
    expected_return_date: date | None
    returned_date: date | None
    created_at: datetime
    updated_at: datetime
    overdue: bool


class OwnerLoanResponse(ViewerLoanResponse):
    loaned_to: str
    notes: str | None


class ViewerBookLoansResponse(BaseModel):
    access: Literal["VIEWER"] = "VIEWER"
    library_id: UUID
    book_id: UUID
    writable: Literal[False] = False
    total_loans: int
    loans: list[ViewerLoanResponse]


class OwnerBookLoansResponse(BaseModel):
    access: Literal["OWNER"] = "OWNER"
    library_id: UUID
    book_id: UUID
    writable: Literal[True] = True
    total_loans: int
    loans: list[OwnerLoanResponse]


class ViewerLoanOverviewResponse(BaseModel):
    access: Literal["VIEWER"] = "VIEWER"
    library_id: UUID
    writable: Literal[False] = False
    total_active: int
    total_overdue: int
    loans: list[ViewerLoanResponse]


class OwnerLoanOverviewResponse(BaseModel):
    access: Literal["OWNER"] = "OWNER"
    library_id: UUID
    writable: Literal[True] = True
    total_active: int
    total_overdue: int
    loans: list[OwnerLoanResponse]


class LoanStatisticsBookResponse(BaseModel):
    book_id: UUID
    title: str
    author: str
    loans: int


class LoanStatisticsYearResponse(BaseModel):
    year: int
    loans: int
    returns: int


class LoanStatisticsResponse(BaseModel):
    active: int
    overdue: int
    completed: int
    unknown_loan_dates: int
    unknown_return_dates: int
    books: list[LoanStatisticsBookResponse]
    years: list[LoanStatisticsYearResponse]

