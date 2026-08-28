from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class BookSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    author: str
    created_at: datetime


class CatalogueResponse(BaseModel):
    library_id: UUID
    books: list[BookSummary]

