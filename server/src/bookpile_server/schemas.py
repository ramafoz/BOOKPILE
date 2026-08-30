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

