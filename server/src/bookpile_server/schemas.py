from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BookSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    author: str
    created_at: datetime


class CatalogueResponse(BaseModel):
    library_id: UUID
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

