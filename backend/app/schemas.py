from enum import Enum
from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class BookStatus(str, Enum):
    pending = "PENDING"
    currently_reading = "CURRENTLY_READING"
    read = "READ"


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


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=300)
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

    @field_validator("notes")
    @classmethod
    def blank_notes_to_none(cls, value: str | None) -> str | None:
        return value.strip() or None if value else None


class BookCreate(BookBase):
    shift_existing: bool = False
    shift_direction: ShiftDirection = ShiftDirection.up


class BookUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=300)
    author: str | None = Field(default=None, min_length=1, max_length=300)
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


class Book(BookBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: str
    updated_at: str
    cover_filename: str | None = None
    location_label: str | None = None
    bookcase_name: str | None = None
    shelf_number: int | None = None
    container_type: ContainerType | None = None
    layer: Layer | None = None
    container_number: int | None = None


class Stats(BaseModel):
    total: int
    pending: int
    currently_reading: int
    read: int


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
    published_date: str | None = None
    page_count: int | None = None
    subjects: list[str]
    language: str | None = None
    edition: str | None = None
    genres: list[str]
    category: str | None = None
    format: str | None = None
    confidence_or_match_notes: str | None = None
    catalogue_matches: list[CatalogueMatch] = Field(default_factory=list)


class ISBNLookupResult(BaseModel):
    isbn: str
    candidates: list[BibliographicCandidate]


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
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)


class VisualBookcaseLayout(VisualRect):
    id: int


class VisualShelfLayout(BaseModel):
    id: int
    height_weight: float = Field(ge=0.25, le=8)


class VisualContainerLayout(BaseModel):
    id: int
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    width: float = Field(gt=0, le=100)
    height: float = Field(gt=0, le=100)


class VisualLayoutUpdate(BaseModel):
    bookcases: list[VisualBookcaseLayout]
    shelves: list[VisualShelfLayout]
    containers: list[VisualContainerLayout]
    outside: VisualRect
