"""Opt-in PostgreSQL gate for Phase 1.

Set BOOKPILE_SERVER_TEST_DATABASE_URL to a disposable database whose name ends
in `_test`. The safety suffix prevents this test from targeting a normal or
production database accidentally.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from bookpile_server.database import get_session
from bookpile_server.config import get_settings
from bookpile_server.main import create_app
from bookpile_server.models import (
    AccountInvitation,
    AccountActionToken,
    Book,
    BookContributor,
    Bookcase,
    Container,
    ContributorRole,
    Library,
    LibraryAuditEvent,
    LibraryInvitation,
    LibraryMembership,
    RateLimitBucket,
    SecurityEvent,
    Shelf,
    User,
    UserSession,
    VisualBookcaseLayout,
    VisualContainerLayout,
    VisualOutsideArea,
    VisualShelfLayout,
)
from bookpile_server.repositories.books import BookRepository
from bookpile_server.repositories.account_invitations import (
    AccountInvitationRepository,
)
from bookpile_server.repositories.account_actions import AccountActionRepository
from bookpile_server.services.account_invitations import (
    AccountInvitationError,
    AccountInvitationService,
)
from bookpile_server.repositories.rate_limits import RateLimitRepository
from bookpile_server.services.rate_limits import (
    RateLimitExceededError,
    RateLimiter,
    RateLimitPolicy,
)
from bookpile_server.services.auth import hash_session_secret


TEST_DATABASE_URL = os.getenv("BOOKPILE_SERVER_TEST_DATABASE_URL")


@pytest.mark.skipif(
    not TEST_DATABASE_URL,
    reason="BOOKPILE_SERVER_TEST_DATABASE_URL is not configured",
)
def test_postgresql_migration_and_tenant_scope() -> None:
    assert TEST_DATABASE_URL is not None
    url = make_url(TEST_DATABASE_URL)
    assert url.get_backend_name() == "postgresql"
    assert (url.database or "").endswith("_test"), (
        "PostgreSQL integration tests require a disposable database ending "
        "in '_test'"
    )

    server_directory = Path(__file__).resolve().parents[1]
    alembic = Config(server_directory / "alembic.ini")
    alembic.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    engine = create_engine(TEST_DATABASE_URL)

    try:
        # Create Phase 1 catalogue rows before 0007 so the migration must
        # preserve real pre-existing IDs, titles, and legacy Author text.
        command.upgrade(alembic, "0006_library_memberships")
        first_library_id = uuid4()
        second_library_id = uuid4()
        first_book_id = uuid4()
        second_book_id = uuid4()
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO libraries (id, name, slug) "
                    "VALUES (:id, :name, :slug)"
                ),
                [
                    {
                        "id": first_library_id,
                        "name": "First",
                        "slug": "postgres-first",
                    },
                    {
                        "id": second_library_id,
                        "name": "Second",
                        "slug": "postgres-second",
                    },
                ],
            )
            connection.execute(
                text(
                    "INSERT INTO books (id, library_id, title, author) "
                    "VALUES (:id, :library_id, :title, :author)"
                ),
                [
                    {
                        "id": first_book_id,
                        "library_id": first_library_id,
                        "title": "One",
                        "author": "Author A",
                    },
                    {
                        "id": second_book_id,
                        "library_id": second_library_id,
                        "title": "Two",
                        "author": "Author B",
                    },
                ],
            )

        command.upgrade(alembic, "head")
        assert {
            "libraries",
            "books",
            "users",
            "user_sessions",
            "security_events",
            "account_invitations",
            "account_action_tokens",
            "rate_limit_buckets",
            "library_memberships",
            "library_invitations",
            "library_audit_events",
            "contributor_roles",
            "book_contributors",
            "bookcases",
            "shelves",
            "containers",
            "visual_bookcase_layouts",
            "visual_shelf_layouts",
            "visual_container_layouts",
            "visual_outside_areas",
        } <= set(inspect(engine).get_table_names())
        with Session(engine) as session:
            first = session.get(Library, first_library_id)
            second = session.get(Library, second_library_id)
            first_book = session.get(Book, first_book_id)
            second_book = session.get(Book, second_book_id)
            assert first is not None
            assert second is not None
            assert first_book is not None
            assert second_book is not None
            assert (first_book.title, first_book.author) == ("One", "Author A")
            assert first_book.translation_status == "UNKNOWN"
            assert first_book.is_original_collection is False
            assert first_book.updated_at is not None

            role_codes = list(
                session.scalars(
                    select(ContributorRole.code).order_by(
                        ContributorRole.sort_order
                    )
                )
            )
            assert role_codes == [
                "AUTHOR",
                "SCRIPTWRITER",
                "TRANSLATOR",
                "ILLUSTRATOR",
                "PENCILLER",
                "INKER",
                "COLORIST",
                "LETTERER",
                "COVER_ARTIST",
                "EDITOR",
                "COORDINATOR",
                "COMPILER",
                "PHOTOGRAPHER",
                "ADAPTER",
                "OTHER",
            ]

            first_bookcase = Bookcase(
                library_id=first.id,
                name="First bookcase",
                height_mm=2100,
                width_mm=800,
                depth_mm=300,
            )
            second_bookcase = Bookcase(
                library_id=second.id,
                name="Second bookcase",
            )
            session.add_all([first_bookcase, second_bookcase])
            session.flush()
            first_shelf = Shelf(
                library_id=first.id,
                bookcase_id=first_bookcase.id,
                shelf_number=1,
                usable_width_mm=760,
            )
            second_shelf = Shelf(
                library_id=second.id,
                bookcase_id=second_bookcase.id,
                shelf_number=1,
            )
            session.add_all([first_shelf, second_shelf])
            session.flush()
            first_container = Container(
                library_id=first.id,
                shelf_id=first_shelf.id,
                container_type="ROW",
                layer="BACKGROUND",
                container_number=1,
            )
            second_container = Container(
                library_id=second.id,
                shelf_id=second_shelf.id,
                container_type="ROW",
                layer="BACKGROUND",
                container_number=1,
            )
            session.add_all([first_container, second_container])
            session.flush()
            second_container_id = second_container.id
            first_book.container_id = first_container.id
            first_book.position = 1
            first_book.page_count = 320
            first_book.language = "Galician"
            first_book.original_language = "English"
            first_book.translation_status = "TRANSLATED"
            first_book.height_mm = 235
            first_book.width_mm = 155
            first_book.thickness_mm = 28
            session.add_all(
                [
                    BookContributor(
                        library_id=first.id,
                        book_id=first_book.id,
                        role_code="AUTHOR",
                        position=1,
                        name="Author A",
                    ),
                    VisualBookcaseLayout(
                        library_id=first.id,
                        bookcase_id=first_bookcase.id,
                        x_mm=Decimal("-400"),
                        floor_y_mm=Decimal("1700"),
                        width_mm=Decimal("500"),
                        height_mm=Decimal("1600"),
                        frame_left_mm=Decimal("12.5"), frame_right_mm=Decimal("12.5"),
                        top_closure_mm=Decimal("40"), bottom_closure_mm=Decimal("40"),
                        separator_thickness_mm=Decimal("12.5"),
                    ),
                    VisualShelfLayout(
                        library_id=first.id,
                        shelf_id=first_shelf.id,
                        height_weight=Decimal("1"),
                        x_mm=Decimal("12.5"), floor_y_mm=Decimal("40"),
                        width_mm=Decimal("475"), height_mm=Decimal("1520"),
                        left_frame_mm=Decimal("12.5"), right_frame_mm=Decimal("12.5"),
                        top_closure_mm=Decimal("40"), bottom_board_mm=Decimal("40"),
                    ),
                    VisualContainerLayout(
                        library_id=first.id,
                        container_id=first_container.id,
                        x=Decimal("0"),
                        y=Decimal("0"),
                        width=Decimal("100"),
                        height=Decimal("100"),
                        row_anchor="LEFT",
                    ),
                    VisualOutsideArea(
                        library_id=first.id,
                        area_kind="READING",
                        x_mm=Decimal("1000"),
                        y_mm=Decimal("1400"),
                        width_mm=Decimal("400"),
                        height_mm=Decimal("360"),
                    ),
                ]
            )
            now = datetime.now(UTC)
            user = User(
                email="reader@example.test",
                username="reader_one",
                password_hash="not-a-real-password-hash",
                state="active",
                email_verified_at=now,
            )
            session.add(user)
            session.flush()
            first.created_by_user_id = user.id
            session.add(
                LibraryMembership(
                    library_id=first.id,
                    user_id=user.id,
                    role="OWNER",
                    selected_reading_user_id=user.id,
                )
            )
            session.add(
                LibraryInvitation(
                    library_id=first.id,
                    token_hash="e" * 64,
                    role="VIEWER",
                    viewer_scope="CATALOG_ONLY",
                    created_by_user_id=user.id,
                    expires_at=now + timedelta(days=7),
                )
            )
            session.add(
                LibraryAuditEvent(
                    library_id=first.id,
                    actor_user_id=user.id,
                    event_type="membership_foundation_test",
                    details={"source": "postgresql-integration"},
                )
            )
            session.add(
                UserSession(
                    user_id=user.id,
                    token_hash=hash_session_secret("postgres-test-session"),
                    csrf_token_hash=hash_session_secret("postgres-test-csrf"),
                    last_seen_at=now,
                    expires_at=now + timedelta(days=7),
                    absolute_expires_at=now + timedelta(days=30),
                )
            )
            session.add(
                SecurityEvent(
                    user_id=user.id,
                    event_type="identity_foundation_test",
                    details={"source": "postgresql-integration"},
                )
            )
            session.add(
                AccountInvitation(
                    token_hash="c" * 64,
                    expires_at=now + timedelta(days=7),
                )
            )
            session.add(
                AccountActionToken(
                    user_id=user.id,
                    purpose="email_verification",
                    token_hash="d" * 64,
                    expires_at=now + timedelta(hours=24),
                )
            )
            session.commit()

            books = BookRepository(session).list_for_library(first.id)
            assert [book.title for book in books] == ["One"]

            app = create_app()

            def override_session():
                yield session

            app.dependency_overrides[get_session] = override_session
            with TestClient(app) as client:
                client.cookies.set(
                    get_settings().session_cookie_name,
                    "postgres-test-session",
                )
                response = client.get(
                    f"/api/v1/libraries/{first.id}/catalogue",
                    params={"search": "one"},
                )
                client.cookies.set(
                    get_settings().csrf_cookie_name,
                    "postgres-test-csrf",
                )
                created_response = client.post(
                    f"/api/v1/libraries/{first.id}/catalogue",
                    headers={"X-CSRF-Token": "postgres-test-csrf"},
                    json={
                        "title": "PostgreSQL catalogue write",
                        "author": "Multiple authors",
                        "isbn_13": "9780441478125",
                        "page_count": 240,
                        "language": "English",
                        "original_language": "Spanish",
                        "translation_status": "TRANSLATED",
                        "genre_text": "Testing; Science Fiction",
                        "contributors": [
                            {"role_code": "AUTHOR", "name": "First Writer"},
                            {"role_code": "AUTHOR", "name": "Second Writer"},
                            {"role_code": "TRANSLATOR", "name": "Translator"},
                        ],
                    },
                )
                placement_response = client.put(
                    f"/api/v1/libraries/{first.id}/physical-library/books/"
                    f"{created_response.json()['id']}/placement",
                    headers={"X-CSRF-Token": "postgres-test-csrf"},
                    json={"container_id": str(first_container.id), "position": 1},
                )
                options_response = client.get(
                    f"/api/v1/libraries/{first.id}/catalogue/metadata-options"
                )
                physical_response = client.get(
                    f"/api/v1/libraries/{first.id}/physical-library"
                )
                postgresql_layout = physical_response.json()["layout"]
                postgresql_layout["containers"][0]["row_anchor"] = "RIGHT"
                layout_response = client.put(
                    f"/api/v1/libraries/{first.id}/physical-library/layout",
                    headers={"X-CSRF-Token": "postgres-test-csrf"},
                    json=postgresql_layout,
                )
                created_bookcase_response = client.post(
                    f"/api/v1/libraries/{first.id}/physical-library/bookcases",
                    headers={"X-CSRF-Token": "postgres-test-csrf"},
                    json={"name": "PostgreSQL physical service"},
                )
                inaccessible_physical_response = client.get(
                    f"/api/v1/libraries/{second.id}/physical-library"
                )
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert [book["title"] for book in response.json()["books"]] == [
                "One"
            ]
            assert "Two" not in response.text
            assert created_response.status_code == 201, created_response.text
            assert created_response.json()["display_author"] == (
                "First Writer & Second Writer"
            )
            assert created_response.json()["genre_text"] == (
                "Science Fiction, Testing"
            )
            assert placement_response.status_code == 200, placement_response.text
            placed_books = {
                item["id"]: item for item in placement_response.json()["books"]
            }
            assert placed_books[str(created_response.json()["id"])]["position"] == 1
            assert placed_books[str(first_book_id)]["position"] == 2
            assert options_response.status_code == 200, options_response.text
            assert options_response.json()["languages"] == ["English", "Galician"]
            assert options_response.json()["genres"] == [
                "Science Fiction",
                "Testing",
            ]
            assert options_response.json()["contributor_roles"][0]["code"] == (
                "AUTHOR"
            )
            assert physical_response.status_code == 200, physical_response.text
            assert physical_response.json()["bookcases"][0]["book_count"] == 2
            assert layout_response.status_code == 200, layout_response.text
            assert layout_response.json()["layout"]["containers"][0][
                "row_anchor"
            ] == "RIGHT"
            assert created_bookcase_response.status_code == 201, (
                created_bookcase_response.text
            )
            assert {
                item["name"]
                for item in created_bookcase_response.json()["bookcases"]
            } == {"First bookcase", "PostgreSQL physical service"}
            assert inaccessible_physical_response.status_code == 404

            locked_action = AccountActionRepository(session).get_token_for_update(
                token_hash="d" * 64,
                purpose="email_verification",
            )
            assert locked_action is not None
            assert locked_action.user.id == user.id

            invitation_result = AccountInvitationService(
                AccountInvitationRepository(session)
            ).create()

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "UPDATE books SET container_id = :container_id, "
                        "position = 2 WHERE id = :book_id"
                    ),
                    {
                        "container_id": second_container_id,
                        "book_id": first_book_id,
                    },
                )

        with pytest.raises(IntegrityError):
            with engine.begin() as connection:
                connection.execute(
                    text(
                        "INSERT INTO book_contributors "
                        "(id, library_id, book_id, role_code, position, name) "
                        "VALUES (:id, :library_id, :book_id, "
                        "'AUTHOR', 2, ' author a ')"
                    ),
                    {
                        "id": uuid4(),
                        "library_id": first_library_id,
                        "book_id": first_book_id,
                    },
                )

        def register_concurrently(number: int) -> bool:
            with Session(engine) as concurrent_session:
                service = AccountInvitationService(
                    AccountInvitationRepository(concurrent_session)
                )
                try:
                    service.register(
                        raw_token=invitation_result.raw_token,
                        email=f"concurrent{number}@example.com",
                        username=f"concurrent_{number}",
                        password="a valid concurrent password",
                        password_confirmation="a valid concurrent password",
                        ip_address="127.0.0.1",
                    )
                except AccountInvitationError:
                    return False
                return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(register_concurrently, (1, 2)))
        assert sorted(results) == [False, True]
        with Session(engine) as session:
            assert (
                session.query(User)
                .filter(User.username.in_(("concurrent_1", "concurrent_2")))
                .count()
                == 1
            )

        def consume_rate_limit_concurrently(_: int) -> bool:
            with Session(engine) as concurrent_session:
                limiter = RateLimiter(
                    RateLimitRepository(concurrent_session), "integration-secret"
                )
                try:
                    limiter.enforce(
                        RateLimitPolicy(
                            "postgres_concurrency", 1, timedelta(minutes=1)
                        ),
                        key="same-logical-key",
                        ip_address="127.0.0.1",
                    )
                except RateLimitExceededError:
                    return False
                return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            rate_results = list(
                executor.map(consume_rate_limit_concurrently, (1, 2))
            )
        assert sorted(rate_results) == [False, True]
        with Session(engine) as session:
            bucket = session.scalar(
                select(RateLimitBucket).where(
                    RateLimitBucket.scope == "postgres_concurrency"
                )
            )
            assert bucket is not None
            assert bucket.attempt_count == 2

        # Prove 0007 is independently reversible and preserves the original
        # Phase 1 catalogue values while removing only Phase 4A structures.
        command.downgrade(alembic, "0006_library_memberships")
        phase_six_tables = set(inspect(engine).get_table_names())
        assert {
            "contributor_roles",
            "book_contributors",
            "bookcases",
            "shelves",
            "containers",
            "visual_bookcase_layouts",
            "visual_shelf_layouts",
            "visual_container_layouts",
            "visual_outside_areas",
        }.isdisjoint(phase_six_tables)
        phase_six_book_columns = {
            column["name"] for column in inspect(engine).get_columns("books")
        }
        assert phase_six_book_columns == {
            "id",
            "library_id",
            "title",
            "author",
            "created_at",
        }
        with engine.connect() as connection:
            assert connection.execute(
                text("SELECT title, author FROM books ORDER BY title")
            ).all() == [
                ("One", "Author A"),
                ("PostgreSQL catalogue write", "Multiple authors"),
                ("Two", "Author B"),
            ]

        # Prove 0006 can be removed without removing Phase 2 security data.
        command.downgrade(alembic, "0005_rate_limit_buckets")
        phase_five_tables = set(inspect(engine).get_table_names())
        assert {
            "library_memberships",
            "library_invitations",
            "library_audit_events",
        }.isdisjoint(phase_five_tables)
        assert "rate_limit_buckets" in phase_five_tables

        # Prove 0005 can be removed without removing account-action tokens.
        command.downgrade(alembic, "0004_account_action_tokens")
        phase_four_tables = set(inspect(engine).get_table_names())
        assert "rate_limit_buckets" not in phase_four_tables
        assert "account_action_tokens" in phase_four_tables

        # Prove 0004 can be removed without removing invitations or identities.
        command.downgrade(alembic, "0003_account_invitations")
        phase_three_tables = set(inspect(engine).get_table_names())
        assert "account_action_tokens" not in phase_three_tables
        assert {"account_invitations", "users"} <= phase_three_tables

        # Prove 0003 can be removed without removing Phase 2 identity records.
        command.downgrade(alembic, "0002_identity_foundation")
        phase_two_tables = set(inspect(engine).get_table_names())
        assert "account_invitations" not in phase_two_tables
        assert {"users", "user_sessions", "security_events"} <= phase_two_tables
        with Session(engine) as session:
            assert session.query(User).count() == 2
            assert sorted(user.state for user in session.query(User)) == [
                "active",
                "invited",
            ]

        # Then prove 0002 can be removed without removing Phase 1 catalogue.
        command.downgrade(alembic, "0001_server_foundation")
        phase_one_tables = set(inspect(engine).get_table_names())
        assert {"libraries", "books"} <= phase_one_tables
        assert {
            "users",
            "user_sessions",
            "security_events",
        }.isdisjoint(phase_one_tables)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM libraries")) == 2
            assert connection.scalar(text("SELECT count(*) FROM books")) == 3
    finally:
        command.downgrade(alembic, "base")
        remaining_tables = set(inspect(engine).get_table_names())
        assert remaining_tables <= {"alembic_version"}
        engine.dispose()

