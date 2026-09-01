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


class PhysicalBookResponse(BaseModel):
    id: UUID
    title: str
    author: str
    page_count: int | None
    container_id: UUID | None
    position: int | None


class VisualBookcaseLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    bookcase_id: UUID
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class VisualShelfLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    shelf_id: UUID
    height_weight: float = Field(ge=0.25, le=8)


class VisualContainerLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    container_id: UUID
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    row_anchor: Literal["LEFT", "RIGHT"] = "LEFT"
    pile_support_kind: Literal["SHELF", "ROW"] | None = None
    pile_support_container_id: UUID | None = None

    @model_validator(mode="after")
    def validate_bounds(self) -> "VisualContainerLayoutWrite":
        if self.x + self.width > 100 or self.y + self.height > 100:
            raise ValueError("Container geometry must remain inside its shelf")
        return self


class VisualOutsideAreaWrite(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    area_kind: Literal["READING", "LOANED"]
    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class VisualLayoutWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision: str = Field(min_length=64, max_length=64)
    bookcases: list[VisualBookcaseLayoutWrite]
    shelves: list[VisualShelfLayoutWrite]
    containers: list[VisualContainerLayoutWrite]
    outside_areas: list[VisualOutsideAreaWrite]


class VisualLayoutResponse(BaseModel):
    revision: str
    bookcases: list[VisualBookcaseLayoutWrite]
    shelves: list[VisualShelfLayoutWrite]
    containers: list[VisualContainerLayoutWrite]
    outside_areas: list[VisualOutsideAreaWrite]


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

