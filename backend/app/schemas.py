from enum import Enum
from datetime import date
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator

from .isbn import normalize_isbn


class BookStatus(str, Enum):
    pending = "PENDING"
    currently_reading = "CURRENTLY_READING"
    read = "READ"


class ReadingSessionState(str, Enum):
    active = "ACTIVE"
    completed = "COMPLETED"


class LoanState(str, Enum):
    active = "ACTIVE"
    returned = "RETURNED"


class FictionCategory(str, Enum):
    fiction = "FICTION"
    non_fiction = "NON_FICTION"


class Binding(str, Enum):
    hardcover = "HARDCOVER"
    paperback = "PAPERBACK"
    flexibound = "FLEXIBOUND"
    spiral = "SPIRAL"
    stapled = "STAPLED"
    other = "OTHER"


class PublicationType(str, Enum):
    conventional_book = "CONVENTIONAL_BOOK"
    comic_graphic_novel = "COMIC_GRAPHIC_NOVEL"
    atlas = "ATLAS"
    reference = "REFERENCE"
    art_photography_illustrated = "ART_PHOTOGRAPHY_ILLUSTRATED"
    magazine_periodical = "MAGAZINE_PERIODICAL"
    other = "OTHER"


class ContainerType(str, Enum):
    row = "ROW"
    pile = "PILE"


class Layer(str, Enum):
    background = "BACKGROUND"
    foreground = "FOREGROUND"


class ShiftDirection(str, Enum):
    up = "UP"
    down = "DOWN"


class OldPositionMode(str, Enum):
    collapse = "COLLAPSE"
    leave_gap = "LEAVE_GAP"


class NewPositionMode(str, Enum):
    squeeze = "SQUEEZE"
    swap = "SWAP"
    continue_chain = "CONTINUE"


class RearrangementDestinationKind(str, Enum):
    physical = "PHYSICAL"
    reading = "READING"


class BookcaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class BookcaseUpdate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("Bookcase name cannot be blank")
        return stripped

    @field_validator("description")
    @classmethod
    def blank_description_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class ShelfCreate(BaseModel):
    bookcase_id: int
    shelf_number: int = Field(gt=0)


class ShelfUpdate(BaseModel):
    shelf_number: int = Field(gt=0)


class ContainerCreate(BaseModel):
    shelf_id: int
    container_type: ContainerType
    layer: Layer
    container_number: int = Field(gt=0)


class ContainerUpdate(BaseModel):
    container_number: int = Field(gt=0)


class BookMove(BaseModel):
    container_id: int
    position: int = Field(gt=0)
    swap_if_occupied: bool = True


class RearrangementStep(BaseModel):
    destination_kind: RearrangementDestinationKind = (
        RearrangementDestinationKind.physical
    )
    container_id: int | None = None
    position: int | None = Field(default=None, gt=0)
    new_position_mode: NewPositionMode = NewPositionMode.squeeze
    reading_exit_status: Literal["PENDING", "READ"] | None = None


class RearrangementOperation(BaseModel):
    book_id: int
    old_position_mode: OldPositionMode = OldPositionMode.collapse
    release_shelf_space: bool = False
    steps: list[RearrangementStep] = Field(default_factory=list, max_length=100)


class RearrangementRequest(RearrangementOperation):
    completed_operations: list[RearrangementOperation] = Field(
        default_factory=list,
        max_length=100,
    )


class RearrangementApplyRequest(RearrangementRequest):
    revision: str = Field(min_length=64, max_length=64)


class RearrangementPlacement(BaseModel):
    book_id: int
    container_id: int | None
    position: int | None
    status: BookStatus


class RearrangementGap(BaseModel):
    container_id: int
    positions: list[int]


class RearrangementContainerLayout(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    id: int
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    row_anchor: Literal["LEFT", "RIGHT"] = "LEFT"
    pile_support_kind: Literal["SHELF", "ROW"] | None = None
    pile_support_container_id: int | None = None


class RearrangementResult(BaseModel):
    revision: str
    valid_to_apply: bool
    complete: bool
    effective_old_position_mode: OldPositionMode
    next_active_book_id: int | None = None
    placements: list[RearrangementPlacement]
    gaps: list[RearrangementGap]
    movement_log: list[str]
    movement_groups: list[list[str]]
    warnings: list[str]
    geometry_errors: list[str] = Field(default_factory=list)
    container_layouts: list[RearrangementContainerLayout] = Field(default_factory=list)


def normalize_optional_isbn(value: str | None, length: int) -> str | None:
    if value is None or not value.strip():
        return None
    normalized = normalize_isbn(value)
    if len(normalized) != length:
        raise ValueError(f"ISBN-{length} must be entered in the ISBN-{length} field")
    return normalized


def normalize_structured_authors(values: list[str]) -> list[str]:
    cleaned = [" ".join(value.split()) for value in values]
    if any(not value for value in cleaned):
        raise ValueError("Author names cannot be blank")
    normalized = [value.casefold() for value in cleaned]
    if len(normalized) != len(set(normalized)):
        raise ValueError("The same author cannot be listed twice")
    return cleaned


def normalize_genre_text(value: str | None) -> str | None:
    if value is None:
        return None
    genres: dict[str, str] = {}
    for item in re.split(r"[,;\r\n]+", value):
        cleaned = " ".join(item.split())
        if cleaned:
            genres.setdefault(cleaned.casefold(), cleaned)
    if not genres:
        return None
    return ", ".join(sorted(genres.values(), key=str.casefold))


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=300)
    has_multiple_authors: bool = False
    structured_authors: list[str] = Field(default_factory=list, max_length=250)
    isbn_10: str | None = Field(default=None, max_length=40)
    isbn_13: str | None = Field(default=None, max_length=40)
    subtitle: str | None = Field(default=None, max_length=500)
    page_count: int | None = Field(default=None, gt=0)
    publisher: str | None = Field(default=None, max_length=300)
    current_ed_year: int | None = Field(default=None, ge=1000, le=9999)
    original_publication_year: int | None = Field(default=None, ge=1000, le=9999)
    language: str | None = Field(default=None, max_length=200)
    edition_number: int | None = Field(default=None, gt=0)
    fiction_category: FictionCategory | None = None
    binding: Binding | None = None
    publication_type: PublicationType | None = None
    genre_text: str | None = Field(default=None, max_length=1000)
    series_name: str | None = Field(default=None, max_length=300)
    series_volume: str | None = Field(default=None, max_length=100)
    status: BookStatus = BookStatus.pending
    goodreads_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=4000)
    acquisition_date: date | None = None
    reading_started_date: date | None = None
    read_date: date | None = None
    is_read_date_unknown: bool = False
    is_original_collection: bool = False
    container_id: int | None = None
    position: int | None = Field(default=None, gt=0)

    @field_validator("title", "author")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        return value.strip()

    @field_validator(
        "notes",
        "subtitle",
        "publisher",
        "language",
        "series_name",
        "series_volume",
    )
    @classmethod
    def blank_notes_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("genre_text")
    @classmethod
    def normalize_genres(cls, value: str | None) -> str | None:
        return normalize_genre_text(value)

    @field_validator("isbn_10")
    @classmethod
    def validate_isbn_10(cls, value: str | None) -> str | None:
        return normalize_optional_isbn(value, 10)

    @field_validator("isbn_13")
    @classmethod
    def validate_isbn_13(cls, value: str | None) -> str | None:
        return normalize_optional_isbn(value, 13)

    @field_validator("structured_authors")
    @classmethod
    def validate_structured_authors(cls, values: list[str]) -> list[str]:
        if any(len(value) > 300 for value in values):
            raise ValueError("Author names cannot exceed 300 characters")
        return normalize_structured_authors(values)

    @model_validator(mode="after")
    def validate_author_structure(self):
        if self.has_multiple_authors:
            if self.author != "Multiple authors":
                raise ValueError(
                    "Multiple-author books require author = Multiple authors"
                )
            if len(self.structured_authors) < 2:
                raise ValueError(
                    "Multiple-author books require at least two authors"
                )
        elif self.structured_authors:
            raise ValueError("Single-author books cannot have structured authors")
        return self


class LoanStartRequest(BaseModel):
    loaned_to: str = Field(min_length=1, max_length=300)
    loaned_date: date | None = None
    expected_return_date: date | None = None
    notes: str | None = Field(default=None, max_length=4000)

    @field_validator("loaned_to")
    @classmethod
    def normalize_loaned_to(cls, value: str) -> str:
        cleaned = " ".join(value.split())
        if not cleaned:
            raise ValueError("Loaned to is required")
        return cleaned

    @field_validator("notes")
    @classmethod
    def normalize_loan_notes(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class LoanReturnRequest(BaseModel):
    returned_date: date | None = None


class LoanHistoryCreate(LoanStartRequest):
    returned_date: date | None = None


class LoanUpdate(LoanHistoryCreate):
    pass


class BookCreate(BookBase):
    shift_existing: bool = False
    shift_direction: ShiftDirection = ShiftDirection.up
    current_loan: LoanStartRequest | None = None


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=300)
    has_multiple_authors: bool | None = None
    structured_authors: list[str] | None = Field(default=None, max_length=250)
    isbn_10: str | None = Field(default=None, max_length=40)
    isbn_13: str | None = Field(default=None, max_length=40)
    subtitle: str | None = Field(default=None, max_length=500)
    page_count: int | None = Field(default=None, gt=0)
    publisher: str | None = Field(default=None, max_length=300)
    current_ed_year: int | None = Field(default=None, ge=1000, le=9999)
    original_publication_year: int | None = Field(default=None, ge=1000, le=9999)
    language: str | None = Field(default=None, max_length=200)
    edition_number: int | None = Field(default=None, gt=0)
    fiction_category: FictionCategory | None = None
    binding: Binding | None = None
    publication_type: PublicationType | None = None
    genre_text: str | None = Field(default=None, max_length=1000)
    series_name: str | None = Field(default=None, max_length=300)
    series_volume: str | None = Field(default=None, max_length=100)
    status: BookStatus | None = None
    goodreads_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=4000)
    acquisition_date: date | None = None
    reading_started_date: date | None = None
    read_date: date | None = None
    is_read_date_unknown: bool | None = None
    is_original_collection: bool | None = None
    container_id: int | None = None
    position: int | None = Field(default=None, gt=0)

    @field_validator("isbn_10")
    @classmethod
    def validate_isbn_10(cls, value: str | None) -> str | None:
        return normalize_optional_isbn(value, 10)

    @field_validator("isbn_13")
    @classmethod
    def validate_isbn_13(cls, value: str | None) -> str | None:
        return normalize_optional_isbn(value, 13)

    @field_validator(
        "notes",
        "subtitle",
        "publisher",
        "language",
        "series_name",
        "series_volume",
    )
    @classmethod
    def blank_optional_text_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None

    @field_validator("genre_text")
    @classmethod
    def normalize_genres(cls, value: str | None) -> str | None:
        return normalize_genre_text(value)

    @field_validator("structured_authors")
    @classmethod
    def validate_structured_authors(
        cls, values: list[str] | None
    ) -> list[str] | None:
        if values is None:
            return None
        if any(len(value) > 300 for value in values):
            raise ValueError("Author names cannot exceed 300 characters")
        return normalize_structured_authors(values)


class Book(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    updated_at: str
    cover_filename: str | None = None
    location_label: str | None = None
    return_location_label: str | None = None
    bookcase_name: str | None = None
    shelf_number: int | None = None
    container_type: ContainerType | None = None
    layer: Layer | None = None
    container_number: int | None = None
    reading_sessions: list["ReadingSession"] = Field(default_factory=list)
    reading_session_count: int = 0
    is_rereading: bool = False
    loans: list["Loan"] = Field(default_factory=list)
    loan_count: int = 0
    active_loan: "Loan | None" = None
    is_on_loan: bool = False


class Stats(BaseModel):
    total: int
    pending: int
    currently_reading: int
    currently_rereading: int = 0
    read: int


class ReadingSession(BaseModel):
    id: int
    book_id: int
    session_number: int
    state: ReadingSessionState
    started_date: date | None = None
    finished_date: date | None = None
    dates_unknown: bool = False
    created_at: str
    updated_at: str


class Loan(BaseModel):
    id: int
    book_id: int
    loaned_to: str
    notes: str | None = None
    state: LoanState
    loaned_date: date | None = None
    expected_return_date: date | None = None
    returned_date: date | None = None
    created_at: str
    updated_at: str


class ReadingStartRequest(BaseModel):
    started_date: date


class ReadingFinishRequest(BaseModel):
    finished_date: date


class ReadingHistoryCreate(BaseModel):
    started_date: date | None = None
    finished_date: date | None = None
    dates_unknown: bool = False

    @model_validator(mode="after")
    def validate_dates(self):
        if self.dates_unknown:
            if self.started_date is not None or self.finished_date is not None:
                raise ValueError("Unknown reading dates must both be empty")
        elif self.started_date is None or self.finished_date is None:
            raise ValueError("Historical readings require both dates")
        return self


class ReadingHistoryUpdate(BaseModel):
    started_date: date | None = None
    finished_date: date | None = None
    dates_unknown: bool = False


class BibliographicIdentifiers(BaseModel):
    isbn_10: str | None = None
    isbn_13: str | None = None


class CatalogueMatch(BaseModel):
    book_id: int
    title: str
    author: str
    status: BookStatus
    cover_filename: str | None = None
    location_label: str | None = None
    match_class: Literal["strong", "possible"]
    reason: str


class BibliographicCandidate(BaseModel):
    source: str
    source_record_id: str | None = None
    identifiers: BibliographicIdentifiers
    title: str
    subtitle: str | None = None
    authors: list[str]
    publisher: str | None = None
    current_ed_year: int | None = None
    original_publication_year: int | None = None
    page_count: int | None = None
    subjects: list[str]
    language: str | None = None
    edition_number: int | None = None
    fiction_category: FictionCategory | None = None
    binding: Binding | None = None
    publication_type: PublicationType | None = None
    genre_text: str | None = None
    series_name: str | None = None
    series_volume: str | None = None
    confidence_or_match_notes: str | None = None
    catalogue_matches: list[CatalogueMatch] = Field(default_factory=list)


class ISBNLookupResult(BaseModel):
    isbn: str
    candidates: list[BibliographicCandidate]
    catalogue_matches: list[CatalogueMatch] = Field(default_factory=list)


class CatalogueMatchRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    authors: list[str] = Field(min_length=1, max_length=20)

    @field_validator("title")
    @classmethod
    def strip_match_title(cls, value: str) -> str:
        return value.strip()

    @field_validator("authors")
    @classmethod
    def strip_match_authors(cls, values: list[str]) -> list[str]:
        stripped = [value.strip() for value in values if value.strip()]
        if not stripped:
            raise ValueError("At least one author is required")
        return stripped


class VisualRect(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    x: float
    y: float
    width: float = Field(gt=0)
    height: float = Field(gt=0)


class VisualBookcaseLayout(VisualRect):
    id: int


class VisualShelfLayout(BaseModel):
    id: int
    height_weight: float = Field(ge=0.25, le=8)


class VisualContainerLayout(BaseModel):
    model_config = ConfigDict(allow_inf_nan=False)

    id: int
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)
    row_anchor: Literal["LEFT", "RIGHT"] = "LEFT"
    pile_support_kind: Literal["SHELF", "ROW"] | None = None
    pile_support_container_id: int | None = None


class VisualLayoutUpdate(BaseModel):
    bookcases: list[VisualBookcaseLayout]
    shelves: list[VisualShelfLayout]
    containers: list[VisualContainerLayout]
    outside: VisualRect
    loaned: VisualRect
