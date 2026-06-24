from enum import Enum
from datetime import date

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


class BookcaseCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)


class ShelfCreate(BaseModel):
    bookcase_id: int
    shelf_number: int = Field(gt=0)


class ContainerCreate(BaseModel):
    shelf_id: int
    container_type: ContainerType
    layer: Layer
    container_number: int = Field(gt=0)


class BookMove(BaseModel):
    container_id: int
    position: int = Field(gt=0)
    swap_if_occupied: bool = True


class BookBase(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    author: str = Field(min_length=1, max_length=300)
    status: BookStatus = BookStatus.pending
    goodreads_url: HttpUrl | None = None
    notes: str | None = Field(default=None, max_length=4000)
    acquisition_date: date | None = None
    reading_started_date: date | None = None
    read_date: date | None = None
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
