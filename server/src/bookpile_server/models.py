from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    CheckConstraint,
    Computed,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        CheckConstraint("username = lower(username)", name="ck_users_username_lowercase"),
        CheckConstraint("email = lower(email)", name="ck_users_email_lowercase"),
        CheckConstraint(
            "state IN ('pending_verification', 'active', 'suspended', "
            "'pending_deletion', 'deleted')",
            name="ck_users_state",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    username: Mapped[str] = mapped_column(String(30), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(512), nullable=False)
    state: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default="pending_verification",
        server_default="pending_verification",
    )
    email_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    show_public_owned_count: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    show_public_read_count: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    sessions: Mapped[list["UserSession"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    security_events: Mapped[list["SecurityEvent"]] = relationship(
        back_populates="user"
    )
    created_account_invitations: Mapped[list["AccountInvitation"]] = relationship(
        foreign_keys="AccountInvitation.created_by_user_id",
        back_populates="created_by_user",
    )
    consumed_account_invitation: Mapped["AccountInvitation | None"] = relationship(
        foreign_keys="AccountInvitation.consumed_by_user_id",
        back_populates="consumed_by_user",
        uselist=False,
    )
    account_action_tokens: Mapped[list["AccountActionToken"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    library_memberships: Mapped[list["LibraryMembership"]] = relationship(
        foreign_keys="LibraryMembership.user_id",
        back_populates="user",
        cascade="all, delete-orphan",
    )


class AccountInvitation(Base):
    __tablename__ = "account_invitations"
    __table_args__ = (
        Index("ix_account_invitations_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    consumed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="SET NULL"),
        unique=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    created_by_user: Mapped[User | None] = relationship(
        foreign_keys=[created_by_user_id],
        back_populates="created_account_invitations",
    )
    consumed_by_user: Mapped[User | None] = relationship(
        foreign_keys=[consumed_by_user_id],
        back_populates="consumed_account_invitation",
    )


class AccountActionToken(Base):
    __tablename__ = "account_action_tokens"
    __table_args__ = (
        CheckConstraint(
            "purpose IN ('email_verification', 'password_reset')",
            name="ck_account_action_tokens_purpose",
        ),
        Index(
            "ix_account_action_tokens_user_purpose",
            "user_id",
            "purpose",
        ),
        Index("ix_account_action_tokens_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    purpose: Mapped[str] = mapped_column(String(32), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    user: Mapped[User] = relationship(back_populates="account_action_tokens")


class RateLimitBucket(Base):
    __tablename__ = "rate_limit_buckets"
    __table_args__ = (
        CheckConstraint(
            "attempt_count > 0", name="ck_rate_limit_buckets_attempt_count"
        ),
        Index("ix_rate_limit_buckets_updated_at", "updated_at"),
    )

    scope: Mapped[str] = mapped_column(String(64), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class UserSession(Base):
    __tablename__ = "user_sessions"
    __table_args__ = (
        Index("ix_user_sessions_user_active", "user_id", "revoked_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    remember_me: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    absolute_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str | None] = mapped_column(String(500))
    ip_address: Mapped[str | None] = mapped_column(String(45))

    user: Mapped[User] = relationship(back_populates="sessions")


class SecurityEvent(Base):
    __tablename__ = "security_events"
    __table_args__ = (
        Index("ix_security_events_user_occurred", "user_id", "occurred_at"),
        Index("ix_security_events_type_occurred", "event_type", "occurred_at"),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    ip_address: Mapped[str | None] = mapped_column(String(45))
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )

    user: Mapped[User | None] = relationship(back_populates="security_events")


class Library(Base):
    __tablename__ = "libraries"
    __table_args__ = (
        CheckConstraint(
            "state IN ('active', 'pending_deletion', 'deleted')",
            name="ck_libraries_state",
        ),
        CheckConstraint(
            "geometry_mode IN ('MANUAL', 'PHYSICAL')",
            name="ck_libraries_geometry_mode",
        ),
        CheckConstraint(
            "coordinate_system_version >= 2",
            name="ck_libraries_coordinate_system_version",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    state: Mapped[str] = mapped_column(
        String(32), nullable=False, default="active", server_default="active"
    )
    geometry_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="MANUAL", server_default="MANUAL"
    )
    coordinate_system_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=2, server_default="2"
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    books: Mapped[list["Book"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    memberships: Mapped[list["LibraryMembership"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )
    invitations: Mapped[list["LibraryInvitation"]] = relationship(
        back_populates="library", cascade="all, delete-orphan"
    )


class LibraryMembership(Base):
    __tablename__ = "library_memberships"
    __table_args__ = (
        CheckConstraint(
            "role IN ('OWNER', 'VIEWER')", name="ck_library_memberships_role"
        ),
        CheckConstraint(
            "viewer_scope IS NULL OR viewer_scope IN "
            "('CATALOG_ONLY', 'CATALOG_AND_MAP')",
            name="ck_library_memberships_viewer_scope_value",
        ),
        CheckConstraint(
            "(role = 'OWNER' AND viewer_scope IS NULL) OR "
            "(role = 'VIEWER' AND viewer_scope IS NOT NULL)",
            name="ck_library_memberships_role_scope",
        ),
        UniqueConstraint(
            "library_id", "user_id", name="uq_library_memberships_library_user"
        ),
        Index("ix_library_memberships_user_role", "user_id", "role"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    viewer_scope: Mapped[str | None] = mapped_column(String(32))
    selected_reading_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    library: Mapped[Library] = relationship(back_populates="memberships")
    user: Mapped[User] = relationship(
        foreign_keys=[user_id], back_populates="library_memberships"
    )
    selected_reading_user: Mapped[User | None] = relationship(
        foreign_keys=[selected_reading_user_id]
    )


class LibraryInvitation(Base):
    __tablename__ = "library_invitations"
    __table_args__ = (
        CheckConstraint(
            "role IN ('OWNER', 'VIEWER')", name="ck_library_invitations_role"
        ),
        CheckConstraint(
            "viewer_scope IS NULL OR viewer_scope IN "
            "('CATALOG_ONLY', 'CATALOG_AND_MAP')",
            name="ck_library_invitations_viewer_scope_value",
        ),
        CheckConstraint(
            "(role = 'OWNER' AND viewer_scope IS NULL) OR "
            "(role = 'VIEWER' AND viewer_scope IS NOT NULL)",
            name="ck_library_invitations_role_scope",
        ),
        Index("ix_library_invitations_library_active", "library_id", "consumed_at"),
        Index("ix_library_invitations_expires_at", "expires_at"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    viewer_scope: Mapped[str | None] = mapped_column(String(32))
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    consumed_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    library: Mapped[Library] = relationship(back_populates="invitations")
    created_by_user: Mapped[User] = relationship(
        foreign_keys=[created_by_user_id]
    )
    consumed_by_user: Mapped[User | None] = relationship(
        foreign_keys=[consumed_by_user_id]
    )


class LibraryAuditEvent(Base):
    __tablename__ = "library_audit_events"
    __table_args__ = (
        Index(
            "ix_library_audit_events_library_occurred",
            "library_id",
            "occurred_at",
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"),
        primary_key=True,
        autoincrement=True,
    )
    library_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    details: Mapped[dict[str, object]] = mapped_column(
        JSON, nullable=False, default=dict, server_default="{}"
    )


class Book(Base):
    __tablename__ = "books"
    __table_args__ = (
        CheckConstraint(
            "isbn_10 IS NULL OR length(isbn_10) = 10",
            name="ck_books_isbn_10_length",
        ),
        CheckConstraint(
            "isbn_13 IS NULL OR length(isbn_13) = 13",
            name="ck_books_isbn_13_length",
        ),
        CheckConstraint(
            "page_count IS NULL OR page_count > 0",
            name="ck_books_page_count",
        ),
        CheckConstraint(
            "current_ed_year IS NULL OR current_ed_year BETWEEN 1000 AND 9999",
            name="ck_books_current_ed_year",
        ),
        CheckConstraint(
            "original_publication_year IS NULL OR "
            "original_publication_year BETWEEN 1000 AND 9999",
            name="ck_books_original_publication_year",
        ),
        CheckConstraint(
            "translation_status IN ('UNKNOWN', 'ORIGINAL', 'TRANSLATED')",
            name="ck_books_translation_status",
        ),
        CheckConstraint(
            "edition_number IS NULL OR edition_number > 0",
            name="ck_books_edition_number",
        ),
        CheckConstraint(
            "fiction_category IS NULL OR "
            "fiction_category IN ('FICTION', 'NON_FICTION')",
            name="ck_books_fiction_category",
        ),
        CheckConstraint(
            "binding IS NULL OR binding IN "
            "('HARDCOVER', 'PAPERBACK', 'FLEXIBOUND', 'SPIRAL', "
            "'STAPLED', 'OTHER')",
            name="ck_books_binding",
        ),
        CheckConstraint(
            "publication_type IS NULL OR publication_type IN "
            "('CONVENTIONAL_BOOK', 'COMIC_GRAPHIC_NOVEL', 'ATLAS', "
            "'REFERENCE', 'ART_PHOTOGRAPHY_ILLUSTRATED', "
            "'MAGAZINE_PERIODICAL', 'OTHER')",
            name="ck_books_publication_type",
        ),
        CheckConstraint(
            "height_mm IS NULL OR height_mm > 0",
            name="ck_books_height_mm",
        ),
        CheckConstraint(
            "width_mm IS NULL OR width_mm > 0",
            name="ck_books_width_mm",
        ),
        CheckConstraint(
            "thickness_mm IS NULL OR thickness_mm > 0",
            name="ck_books_thickness_mm",
        ),
        CheckConstraint(
            "(container_id IS NULL AND position IS NULL) OR "
            "(container_id IS NOT NULL AND position IS NOT NULL)",
            name="ck_books_location_pair",
        ),
        ForeignKeyConstraint(
            ["library_id", "container_id"],
            ["containers.library_id", "containers.id"],
            name="fk_books_library_container",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("library_id", "id", name="uq_books_library_id"),
        UniqueConstraint(
            "container_id", "position", name="uq_books_container_position"
        ),
        Index("ix_books_library_title", "library_id", "title"),
        Index("ix_books_library_author", "library_id", "author"),
        Index("ix_books_library_isbn_10", "library_id", "isbn_10"),
        Index("ix_books_library_isbn_13", "library_id", "isbn_13"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("libraries.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    author: Mapped[str] = mapped_column(String(500), nullable=False)
    isbn_10: Mapped[str | None] = mapped_column(String(10))
    isbn_13: Mapped[str | None] = mapped_column(String(13))
    subtitle: Mapped[str | None] = mapped_column(String(500))
    page_count: Mapped[int | None] = mapped_column(Integer)
    publisher: Mapped[str | None] = mapped_column(String(300))
    current_ed_year: Mapped[int | None] = mapped_column(Integer)
    original_publication_year: Mapped[int | None] = mapped_column(Integer)
    language: Mapped[str | None] = mapped_column(String(200))
    original_language: Mapped[str | None] = mapped_column(String(200))
    translation_status: Mapped[str] = mapped_column(
        String(16), nullable=False, default="UNKNOWN", server_default="UNKNOWN"
    )
    edition_number: Mapped[int | None] = mapped_column(Integer)
    fiction_category: Mapped[str | None] = mapped_column(String(16))
    binding: Mapped[str | None] = mapped_column(String(32))
    publication_type: Mapped[str | None] = mapped_column(String(48))
    genre_text: Mapped[str | None] = mapped_column(String(1000))
    series_name: Mapped[str | None] = mapped_column(String(300))
    series_volume: Mapped[str | None] = mapped_column(String(100))
    goodreads_url: Mapped[str | None] = mapped_column(String(2048))
    notes: Mapped[str | None] = mapped_column(Text)
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    is_original_collection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    height_mm: Mapped[int | None] = mapped_column(Integer)
    width_mm: Mapped[int | None] = mapped_column(Integer)
    thickness_mm: Mapped[int | None] = mapped_column(Integer)
    container_id: Mapped[UUID | None] = mapped_column(Uuid)
    position: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    library: Mapped[Library] = relationship(back_populates="books")
    cover: Mapped["BookCover | None"] = relationship(
        back_populates="book", cascade="all, delete-orphan", uselist=False, lazy="selectin"
    )


class BookCover(Base):
    __tablename__ = "book_covers"
    __table_args__ = (
        CheckConstraint("media_type = 'image/webp'", name="ck_book_covers_media_type"),
        CheckConstraint("byte_size > 0", name="ck_book_covers_byte_size"),
        CheckConstraint("width_px > 0", name="ck_book_covers_width_px"),
        CheckConstraint("height_px > 0", name="ck_book_covers_height_px"),
        CheckConstraint("length(sha256) = 64", name="ck_book_covers_sha256"),
        ForeignKeyConstraint(
            ["library_id", "book_id"], ["books.library_id", "books.id"],
            name="fk_book_covers_library_book", ondelete="CASCADE",
        ),
        UniqueConstraint("book_id", name="uq_book_covers_book_id"),
        Index("ix_book_covers_library_id", "library_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    book_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    object_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    media_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="image/webp", server_default="image/webp"
    )
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    width_px: Mapped[int] = mapped_column(Integer, nullable=False)
    height_px: Mapped[int] = mapped_column(Integer, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    uploaded_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    book: Mapped[Book] = relationship(back_populates="cover")


class ContributorRole(Base):
    __tablename__ = "contributor_roles"
    __table_args__ = (
        CheckConstraint("length(trim(code)) > 0", name="ck_contributor_roles_code"),
        CheckConstraint("length(trim(label)) > 0", name="ck_contributor_roles_label"),
        CheckConstraint("sort_order > 0", name="ck_contributor_roles_sort_order"),
    )

    code: Mapped[str] = mapped_column(String(40), primary_key=True)
    label: Mapped[str] = mapped_column(String(80), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False)
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default="true"
    )


class Bookcase(Base):
    __tablename__ = "bookcases"
    __table_args__ = (
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 160", name="ck_bookcases_name"
        ),
        CheckConstraint(
            "height_mm IS NULL OR height_mm > 0", name="ck_bookcases_height_mm"
        ),
        CheckConstraint(
            "width_mm IS NULL OR width_mm > 0", name="ck_bookcases_width_mm"
        ),
        CheckConstraint(
            "depth_mm IS NULL OR depth_mm > 0", name="ck_bookcases_depth_mm"
        ),
        UniqueConstraint("library_id", "id", name="uq_bookcases_library_id"),
        UniqueConstraint("library_id", "name", name="uq_bookcases_library_name"),
        Index("ix_bookcases_library_id", "library_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(
        Uuid, ForeignKey("libraries.id", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500))
    height_mm: Mapped[int | None] = mapped_column(Integer)
    width_mm: Mapped[int | None] = mapped_column(Integer)
    depth_mm: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Shelf(Base):
    __tablename__ = "shelves"
    __table_args__ = (
        CheckConstraint("shelf_number > 0", name="ck_shelves_number"),
        CheckConstraint(
            "usable_height_mm IS NULL OR usable_height_mm > 0",
            name="ck_shelves_usable_height_mm",
        ),
        CheckConstraint(
            "usable_width_mm IS NULL OR usable_width_mm > 0",
            name="ck_shelves_usable_width_mm",
        ),
        CheckConstraint(
            "usable_depth_mm IS NULL OR usable_depth_mm > 0",
            name="ck_shelves_usable_depth_mm",
        ),
        ForeignKeyConstraint(
            ["library_id", "bookcase_id"],
            ["bookcases.library_id", "bookcases.id"],
            name="fk_shelves_library_bookcase",
            ondelete="CASCADE",
        ),
        UniqueConstraint("library_id", "id", name="uq_shelves_library_id"),
        UniqueConstraint(
            "bookcase_id", "shelf_number", name="uq_shelves_bookcase_number"
        ),
        Index("ix_shelves_library_bookcase", "library_id", "bookcase_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    bookcase_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    shelf_number: Mapped[int] = mapped_column(Integer, nullable=False)
    usable_height_mm: Mapped[int | None] = mapped_column(Integer)
    usable_width_mm: Mapped[int | None] = mapped_column(Integer)
    usable_depth_mm: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Container(Base):
    __tablename__ = "containers"
    __table_args__ = (
        CheckConstraint(
            "container_type IN ('ROW', 'PILE')", name="ck_containers_type"
        ),
        CheckConstraint(
            "layer IN ('BACKGROUND', 'FOREGROUND')", name="ck_containers_layer"
        ),
        CheckConstraint("container_number > 0", name="ck_containers_number"),
        ForeignKeyConstraint(
            ["library_id", "shelf_id"],
            ["shelves.library_id", "shelves.id"],
            name="fk_containers_library_shelf",
            ondelete="CASCADE",
        ),
        UniqueConstraint("library_id", "id", name="uq_containers_library_id"),
        UniqueConstraint(
            "shelf_id",
            "container_type",
            "layer",
            "container_number",
            name="uq_containers_shelf_identity",
        ),
        Index("ix_containers_library_shelf", "library_id", "shelf_id"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    shelf_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    container_type: Mapped[str] = mapped_column(String(8), nullable=False)
    layer: Mapped[str] = mapped_column(String(16), nullable=False)
    container_number: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class BookContributor(Base):
    __tablename__ = "book_contributors"
    __table_args__ = (
        CheckConstraint("position > 0", name="ck_book_contributors_position"),
        CheckConstraint(
            "length(trim(name)) BETWEEN 1 AND 300",
            name="ck_book_contributors_name",
        ),
        ForeignKeyConstraint(
            ["library_id", "book_id"],
            ["books.library_id", "books.id"],
            name="fk_book_contributors_library_book",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "book_id", "role_code", "position", name="uq_book_contributors_position"
        ),
        UniqueConstraint(
            "book_id",
            "role_code",
            "normalized_name",
            name="uq_book_contributors_normalized_name",
        ),
        Index("ix_book_contributors_library_book", "library_id", "book_id"),
        Index("ix_book_contributors_role_name", "role_code", "name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    library_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    book_id: Mapped[UUID] = mapped_column(Uuid, nullable=False)
    role_code: Mapped[str] = mapped_column(
        String(40), ForeignKey("contributor_roles.code", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(300), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        String(300), Computed("lower(trim(name))", persisted=True)
    )


class VisualBookcaseLayout(Base):
    __tablename__ = "visual_bookcase_layouts"
    __table_args__ = (
        CheckConstraint("width_mm > 0", name="ck_visual_bookcase_width"),
        CheckConstraint("height_mm > 0", name="ck_visual_bookcase_height"),
        CheckConstraint(
            "shelf_direction IN ('TOP_TO_BOTTOM','BOTTOM_TO_TOP','LEFT_TO_RIGHT','RIGHT_TO_LEFT')",
            name="ck_visual_bookcase_shelf_direction",
        ),
        CheckConstraint(
            "frame_left_mm >= 0 AND frame_right_mm >= 0 AND "
            "top_closure_mm >= 0 AND bottom_closure_mm >= 0 AND "
            "separator_thickness_mm >= 5",
            name="ck_visual_bookcase_structure_nonnegative",
        ),
        ForeignKeyConstraint(
            ["library_id", "bookcase_id"],
            ["bookcases.library_id", "bookcases.id"],
            name="fk_visual_bookcase_library_bookcase",
            ondelete="CASCADE",
        ),
    )

    library_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    bookcase_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    x_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    floor_y_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    width_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    height_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    shelf_direction: Mapped[str] = mapped_column(String(24), nullable=False, default="TOP_TO_BOTTOM")
    homogeneous_structure: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    frame_left_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    frame_right_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    top_closure_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    bottom_closure_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    separator_thickness_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)


class VisualShelfLayout(Base):
    __tablename__ = "visual_shelf_layouts"
    __table_args__ = (
        CheckConstraint("height_weight > 0", name="ck_visual_shelf_weight"),
        CheckConstraint("width_mm > 0 AND height_mm > 0", name="ck_visual_shelf_size_positive"),
        CheckConstraint(
            "left_frame_mm >= 0 AND right_frame_mm >= 0 AND "
            "top_closure_mm >= 0 AND bottom_board_mm >= 0",
            name="ck_visual_shelf_frames_nonnegative",
        ),
        CheckConstraint("alignment IN ('LEFT','CENTER','RIGHT')", name="ck_visual_shelf_alignment"),
        CheckConstraint(
            "width_source IN ('ENTERED','FALLBACK','DERIVED') AND "
            "height_source IN ('ENTERED','FALLBACK','DERIVED')",
            name="ck_visual_shelf_sources",
        ),
        CheckConstraint(
            "separator_anchor IN ('TOP','BOTTOM') AND "
            "(separator_after_mm IS NULL OR separator_after_mm >= 5) AND "
            "(separator_height_mm IS NULL OR separator_height_mm >= 5) AND "
            "(separator_source IS NULL OR separator_source IN ('ENTERED','FALLBACK','DERIVED'))",
            name="ck_visual_shelf_separator",
        ),
        ForeignKeyConstraint(
            ["library_id", "shelf_id"],
            ["shelves.library_id", "shelves.id"],
            name="fk_visual_shelf_library_shelf",
            ondelete="CASCADE",
        ),
    )

    library_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    shelf_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    height_weight: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    x_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    floor_y_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    width_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    height_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    alignment: Mapped[str] = mapped_column(String(8), nullable=False, default="CENTER")
    offset_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    width_source: Mapped[str] = mapped_column(String(10), nullable=False, default="DERIVED")
    height_source: Mapped[str] = mapped_column(String(10), nullable=False, default="DERIVED")
    open_top: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    left_frame_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    right_frame_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    top_closure_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    bottom_board_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    separator_after_mm: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    separator_anchor: Mapped[str] = mapped_column(String(8), nullable=False, default="BOTTOM")
    separator_height_mm: Mapped[Decimal | None] = mapped_column(Numeric(14, 4))
    separator_source: Mapped[str | None] = mapped_column(String(10))


class VisualContainerLayout(Base):
    __tablename__ = "visual_container_layouts"
    __table_args__ = (
        CheckConstraint("width > 0", name="ck_visual_container_width_positive"),
        CheckConstraint("height > 0", name="ck_visual_container_height_positive"),
        CheckConstraint(
            "row_anchor IN ('LEFT', 'RIGHT')", name="ck_visual_container_anchor"
        ),
        CheckConstraint(
            "support_kind IN ('SHELF', 'CONTAINER')",
            name="ck_visual_container_support_kind",
        ),
        CheckConstraint(
            "(support_kind = 'SHELF' AND support_container_id IS NULL) OR "
            "(support_kind = 'CONTAINER' AND support_container_id IS NOT NULL)",
            name="ck_visual_container_support_pair",
        ),
        CheckConstraint(
            "support_container_id IS NULL OR support_container_id <> container_id",
            name="ck_visual_container_not_self_supported",
        ),
        CheckConstraint(
            "pile_alignment IN ('LEFT', 'CENTER', 'RIGHT')",
            name="ck_visual_container_pile_alignment",
        ),
        ForeignKeyConstraint(
            ["library_id", "container_id"],
            ["containers.library_id", "containers.id"],
            name="fk_visual_container_library_container",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["library_id", "support_container_id"],
            ["containers.library_id", "containers.id"],
            name="fk_visual_container_library_support",
            ondelete="RESTRICT",
        ),
    )

    library_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    container_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    x: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    y: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    width: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    height: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    row_anchor: Mapped[str] = mapped_column(
        String(8), nullable=False, default="LEFT", server_default="LEFT"
    )
    support_kind: Mapped[str] = mapped_column(
        String(16), nullable=False, default="SHELF", server_default="SHELF"
    )
    support_container_id: Mapped[UUID | None] = mapped_column(Uuid)
    pile_alignment: Mapped[str] = mapped_column(
        String(8), nullable=False, default="RIGHT", server_default="RIGHT"
    )


class VisualOutsideArea(Base):
    __tablename__ = "visual_outside_areas"
    __table_args__ = (
        CheckConstraint(
            "area_kind IN ('READING', 'LOANED')", name="ck_visual_outside_kind"
        ),
        CheckConstraint("width_mm > 0", name="ck_visual_outside_width"),
        CheckConstraint("height_mm > 0", name="ck_visual_outside_height"),
        ForeignKeyConstraint(
            ["library_id"], ["libraries.id"], ondelete="CASCADE"
        ),
    )

    library_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    area_kind: Mapped[str] = mapped_column(String(16), primary_key=True)
    x_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    y_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    width_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)
    height_mm: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False)

