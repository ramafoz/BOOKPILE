"""Opt-in PostgreSQL gate for Phase 1.

Set BOOKPILE_SERVER_TEST_DATABASE_URL to a disposable database whose name ends
in `_test`. The safety suffix prevents this test from targeting a normal or
production database accidentally.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from multiprocessing import get_context
from pathlib import Path
from time import monotonic, sleep
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker

from bookpile_server.api import dependencies as api_dependencies
from bookpile_server.config import Settings, get_settings
from bookpile_server.database import get_session
from bookpile_server.general_api_limits import GeneralApiRateLimitMiddleware
from bookpile_server.main import create_app
from bookpile_server.models import (
    AccountStorageEntitlement,
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
    Loan,
    PersonalBookRecord,
    OperationLease,
    RateLimitBucket,
    ReadingSession,
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
from bookpile_server.repositories.readings import ReadingRepository
from bookpile_server.repositories.loans import LoanRepository
from bookpile_server.repositories.storage import StorageRepository
from bookpile_server.repositories.account_invitations import (
    AccountInvitationRepository,
)
from bookpile_server.repositories.account_actions import AccountActionRepository
from bookpile_server.services.account_invitations import (
    AccountInvitationError,
    AccountInvitationService,
)
from bookpile_server.repositories.operation_leases import OperationLeaseRepository
from bookpile_server.services.operation_leases import (
    LeaseRequest,
    OperationLeaseManager,
    OperationLeaseUnavailableError,
    RenewableOperationLeaseGuard,
)
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.services.readings import ReadingConflictError, ReadingService
from bookpile_server.services.loans import LoanConflictError, LoanService
from bookpile_server.services.storage import StorageService
from bookpile_server.services.storage_accounting import calculate_library_logical_bytes
from bookpile_server.services.storage_domain import InsufficientSharedCapacity


TEST_DATABASE_URL = os.getenv("BOOKPILE_SERVER_TEST_DATABASE_URL")


def _request_general_api_limit_from_process(
    database_url: str,
    ready_queue,
    start_event,
    result_queue,
) -> None:
    """Exercise one independent API-worker middleware stack."""
    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        deployment_revision="git-postgres-multiprocess",
        rate_limit_key_secret="integration-secret",
        general_api_limit_mode="enforce",
    ).model_copy(update={"general_api_attempts_per_ip_per_minute": 1})
    app = FastAPI()
    app.add_middleware(
        GeneralApiRateLimitMiddleware,
        settings=settings,
        session_factory=factory,
    )
    try:
        with TestClient(app, client=("198.51.100.24", 12345)) as client:
            ready_queue.put(os.getpid())
            if not start_event.wait(timeout=30):
                raise RuntimeError("Multiprocess limit gate did not start")
            response = client.get("/api/v1/not-a-route")
            result_queue.put(
                (
                    os.getpid(),
                    response.status_code,
                    response.json(),
                    response.headers.get("retry-after"),
                )
            )
    finally:
        engine.dispose()


def _request_mutation_limit_from_process(
    database_url: str,
    raw_session_token: str,
    library_id: str,
    user_mode: str,
    library_mode: str,
    ready_queue,
    start_event,
    result_queue,
) -> None:
    """Exercise one independent mutation-dependency worker stack."""
    engine = create_engine(database_url)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        environment="test",
        database_url=database_url,
        deployment_revision="git-mutation-multiprocess",
        rate_limit_key_secret="integration-secret",
        mutation_user_limit_mode=user_mode,
        mutation_library_limit_mode=library_mode,
    ).model_copy(
        update={
            "mutation_attempts_per_user_per_15_minutes": 1,
            "mutation_attempts_per_library_per_15_minutes": 1,
        }
    )
    api_dependencies.get_settings = lambda: settings
    app = FastAPI()

    def override_session():
        with factory() as session:
            yield session

    app.dependency_overrides[get_session] = override_session

    @app.put(
        "/api/v1/libraries/{library_id}/mutation-probe",
        name=(
            "select_reading_perspective"
            if library_mode != "off"
            else "update_preferred_locale"
        ),
        dependencies=[Depends(api_dependencies.apply_mutation_limits)],
    )
    def mutation_probe(library_id: str) -> dict[str, str]:
        return {"status": "accepted", "library_id": library_id}

    try:
        with TestClient(app, client=("198.51.100.24", 12345)) as client:
            client.cookies.set(settings.session_cookie_name, raw_session_token)
            ready_queue.put(os.getpid())
            if not start_event.wait(timeout=30):
                raise RuntimeError("Multiprocess mutation gate did not start")
            response = client.put(f"/api/v1/libraries/{library_id}/mutation-probe")
            result_queue.put(
                (
                    os.getpid(),
                    response.status_code,
                    response.json(),
                    response.headers.get("retry-after"),
                )
            )
    finally:
        engine.dispose()


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

        # Phase 5E must never silently discard an unexpected legacy shared
        # Goodreads value. Prove the guard aborts, then clear the synthetic
        # value and finish the migration.
        command.upgrade(alembic, "0012_personal_readings")
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE books SET goodreads_url = :url WHERE id = :id"),
                {
                    "id": first_book_id,
                    "url": "https://www.goodreads.com/review/show/legacy",
                },
            )
        with pytest.raises(RuntimeError, match="require manual migration"):
            command.upgrade(alembic, "head")
        with engine.begin() as connection:
            connection.execute(
                text("UPDATE books SET goodreads_url = NULL WHERE id = :id"),
                {"id": first_book_id},
            )
        command.upgrade(alembic, "head")
        assert "goodreads_url" not in {
            column["name"] for column in inspect(engine).get_columns("books")
        }
        assert {
            "libraries",
            "books",
            "users",
            "user_sessions",
            "security_events",
            "account_invitations",
            "account_action_tokens",
            "email_outbox_messages",
            "rate_limit_buckets",
            "operation_leases",
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
            "reading_sessions",
            "personal_book_records",
            "loans",
            "user_profiles",
            "user_profile_field_visibilities",
            "user_profile_images",
            "account_storage_entitlements",
            "library_storage_usages",
            "library_storage_allocations",
            "library_deletion_tombstones",
        } <= set(inspect(engine).get_table_names())
        email_outbox_columns = {
            column["name"]
            for column in inspect(engine).get_columns("email_outbox_messages")
        }
        assert {"smtp_response_code", "provider_queue_id"} <= email_outbox_columns
        user_columns = {column["name"] for column in inspect(engine).get_columns("users")}
        assert "preferred_locale" in user_columns
        command.downgrade(alembic, "0021_email_outbox")
        downgraded_user_columns = {
            column["name"] for column in inspect(engine).get_columns("users")
        }
        assert "preferred_locale" not in downgraded_user_columns
        assert "operation_leases" not in set(inspect(engine).get_table_names())
        downgraded_email_columns = {
            column["name"]
            for column in inspect(engine).get_columns("email_outbox_messages")
        }
        assert {"smtp_response_code", "provider_queue_id"}.isdisjoint(
            downgraded_email_columns
        )
        command.upgrade(alembic, "head")
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
            session.add_all(
                [
                    ReadingSession(
                        library_id=first.id,
                        book_id=first_book.id,
                        user_id=user.id,
                        state="COMPLETED",
                        dates_unknown=True,
                    ),
                    PersonalBookRecord(
                        library_id=first.id,
                        book_id=first_book.id,
                        user_id=user.id,
                        goodreads_url="https://www.goodreads.com/review/show/1",
                    ),
                ]
            )
            session.commit()

            def start_same_copy_concurrently(number: int) -> bool:
                try:
                    with Session(engine, expire_on_commit=False) as concurrent_session:
                        ReadingService(ReadingRepository(concurrent_session)).start(
                            library_id=first.id,
                            book_id=first_book.id,
                            actor_user_id=user.id,
                            started=date(2026, 9, number),
                        )
                except ReadingConflictError:
                    return False
                return True

            with ThreadPoolExecutor(max_workers=2) as executor:
                reading_results = list(
                    executor.map(start_same_copy_concurrently, (1, 2))
                )
            assert sorted(reading_results) == [False, True]
            assert (
                session.query(ReadingSession)
                .filter(ReadingSession.state == "ACTIVE")
                .count()
                == 1
            )

            loan_race_book = Book(
                library_id=first.id,
                title="Loan race",
                author="Concurrency",
            )
            session.add(loan_race_book)
            session.commit()

            def loan_same_copy_concurrently(number: int) -> bool:
                try:
                    with Session(engine, expire_on_commit=False) as concurrent_session:
                        LoanService(LoanRepository(concurrent_session)).start(
                            library_id=first.id,
                            book_id=loan_race_book.id,
                            actor_user_id=user.id,
                            loaned_to=f"Borrower {number}",
                            notes=None,
                            loaned_date=None,
                            expected_return_date=None,
                        )
                except LoanConflictError:
                    return False
                return True

            with ThreadPoolExecutor(max_workers=2) as executor:
                loan_results = list(
                    executor.map(loan_same_copy_concurrently, (1, 2))
                )
            assert sorted(loan_results) == [False, True]
            assert (
                session.query(Loan)
                .filter(Loan.book_id == loan_race_book.id, Loan.state == "ACTIVE")
                .count()
                == 1
            )
            session.query(Loan).filter(Loan.book_id == loan_race_book.id).delete()
            session.delete(loan_race_book)
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

        process_context = get_context("spawn")
        ready_queue = process_context.Queue()
        start_event = process_context.Event()
        result_queue = process_context.Queue()
        workers = [
            process_context.Process(
                target=_request_general_api_limit_from_process,
                args=(
                    TEST_DATABASE_URL,
                    ready_queue,
                    start_event,
                    result_queue,
                ),
            )
            for _ in range(2)
        ]
        try:
            for worker in workers:
                worker.start()
            ready_processes = {ready_queue.get(timeout=30) for _ in workers}
            assert len(ready_processes) == 2
            start_event.set()
            process_results = [result_queue.get(timeout=30) for _ in workers]
        finally:
            start_event.set()
            for worker in workers:
                worker.join(timeout=30)
                if worker.is_alive():
                    worker.terminate()
                    worker.join(timeout=5)

        assert {result[0] for result in process_results} == ready_processes
        assert sorted(result[1] for result in process_results) == [404, 429]
        blocked_result = next(
            result for result in process_results if result[1] == 429
        )
        assert blocked_result[2] == {
            "detail": "Too many requests. Try again later."
        }
        assert blocked_result[3] is not None
        assert int(blocked_result[3]) > 0
        assert all(worker.exitcode == 0 for worker in workers)
        with Session(engine) as session:
            bucket = session.scalar(
                select(RateLimitBucket).where(
                    RateLimitBucket.scope == "general_api_ip"
                )
            )
            assert bucket is not None
            assert bucket.attempt_count == 2
            events = list(
                session.scalars(
                    select(SecurityEvent).where(
                        SecurityEvent.event_type == "rate_limit_blocked",
                        SecurityEvent.details["scope"].as_string()
                        == "general_api_ip",
                    )
                )
            )
            assert len(events) == 1
            event = events[0]
            assert event.ip_address is None
            assert event.details == {
                "scope": "general_api_ip",
                "mode": "enforce",
                "deployment_revision": "git-postgres-multiprocess",
            }

        mutation_coowner_token = "postgres-mutation-coowner-session"
        with Session(engine, expire_on_commit=False) as session:
            mutation_coowner = User(
                email="mutation-coowner@example.test",
                username="mutation_coowner",
                password_hash="not-a-real-password-hash",
                state="active",
                email_verified_at=datetime.now(UTC),
            )
            session.add(mutation_coowner)
            session.flush()
            mutation_coowner_id = mutation_coowner.id
            session.add_all(
                (
                    LibraryMembership(
                        library_id=first_library_id,
                        user_id=mutation_coowner.id,
                        role="OWNER",
                        selected_reading_user_id=mutation_coowner.id,
                    ),
                    UserSession(
                        user_id=mutation_coowner.id,
                        token_hash=hash_session_secret(mutation_coowner_token),
                        csrf_token_hash=hash_session_secret(
                            "postgres-mutation-coowner-csrf"
                        ),
                        last_seen_at=datetime.now(UTC),
                        expires_at=datetime.now(UTC) + timedelta(days=7),
                        absolute_expires_at=datetime.now(UTC) + timedelta(days=30),
                    ),
                )
            )
            session.commit()

        def exercise_mutation_workers(
            tokens: tuple[str, str], *, user_mode: str, library_mode: str
        ) -> list[tuple[int, int, dict[str, str], str | None]]:
            context = get_context("spawn")
            ready = context.Queue()
            start = context.Event()
            results = context.Queue()
            processes = [
                context.Process(
                    target=_request_mutation_limit_from_process,
                    args=(
                        TEST_DATABASE_URL,
                        token,
                        str(first_library_id),
                        user_mode,
                        library_mode,
                        ready,
                        start,
                        results,
                    ),
                )
                for token in tokens
            ]
            try:
                for process in processes:
                    process.start()
                ready_processes = {ready.get(timeout=30) for _ in processes}
                assert len(ready_processes) == 2
                start.set()
                responses = [results.get(timeout=30) for _ in processes]
            finally:
                start.set()
                for process in processes:
                    process.join(timeout=30)
                    if process.is_alive():
                        process.terminate()
                        process.join(timeout=5)
            assert {response[0] for response in responses} == ready_processes
            assert all(process.exitcode == 0 for process in processes)
            return responses

        user_limit_results = exercise_mutation_workers(
            ("postgres-test-session", "postgres-test-session"),
            user_mode="enforce",
            library_mode="off",
        )
        assert sorted(result[1] for result in user_limit_results) == [200, 429]
        user_blocked = next(
            result for result in user_limit_results if result[1] == 429
        )
        assert user_blocked[2] == {
            "detail": "Too many requests. Try again later."
        }
        assert user_blocked[3] is not None

        library_limit_results = exercise_mutation_workers(
            ("postgres-test-session", mutation_coowner_token),
            user_mode="off",
            library_mode="enforce",
        )
        assert sorted(result[1] for result in library_limit_results) == [200, 429]
        library_blocked = next(
            result for result in library_limit_results if result[1] == 429
        )
        assert library_blocked[2] == {
            "detail": "Too many requests. Try again later."
        }
        assert library_blocked[3] is not None

        with Session(engine) as session:
            mutation_buckets = {
                bucket.scope: bucket
                for bucket in session.scalars(
                    select(RateLimitBucket).where(
                        RateLimitBucket.scope.in_(
                            ("mutation_user", "mutation_library")
                        )
                    )
                )
            }
            assert mutation_buckets["mutation_user"].attempt_count == 2
            assert mutation_buckets["mutation_library"].attempt_count == 2
            mutation_events = list(
                session.scalars(
                    select(SecurityEvent).where(
                        SecurityEvent.event_type == "rate_limit_blocked",
                        SecurityEvent.details["scope"].as_string().in_(
                            ("mutation_user", "mutation_library")
                        ),
                    )
                )
            )
            assert len(mutation_events) == 2
            assert {event.details["scope"] for event in mutation_events} == {
                "mutation_user",
                "mutation_library",
            }
            assert all(event.ip_address is None for event in mutation_events)
            assert all(
                event.details["deployment_revision"]
                == "git-mutation-multiprocess"
                for event in mutation_events
            )

        # This identity exists only for the two-Owner race. Remove it before
        # the historical downgrade assertions, whose original two-user
        # fixture is itself part of the migration contract.
        with Session(engine) as session:
            mutation_coowner = session.get(User, mutation_coowner_id)
            assert mutation_coowner is not None
            session.delete(mutation_coowner)
            session.commit()

        def acquire_operation_lease_concurrently(_: int) -> bool:
            with Session(engine) as concurrent_session:
                manager = OperationLeaseManager(
                    OperationLeaseRepository(concurrent_session),
                    "integration-secret",
                    ttl=timedelta(minutes=2),
                )
                try:
                    manager.acquire(
                        [LeaseRequest("postgres_import", "same-library")],
                    )
                except OperationLeaseUnavailableError:
                    return False
                return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            lease_results = list(
                executor.map(acquire_operation_lease_concurrently, (1, 2))
            )
        assert sorted(lease_results) == [False, True]
        with Session(engine) as session:
            lease = session.scalar(
                select(OperationLease).where(
                    OperationLease.scope == "postgres_import"
                )
            )
            assert lease is not None
            assert lease.fencing_token == 1

        with Session(engine) as session:
            manager = OperationLeaseManager(
                OperationLeaseRepository(session),
                "integration-secret",
                ttl=timedelta(seconds=4),
            )
            handles = manager.acquire(
                [LeaseRequest("postgres_heartbeat", "same-library")]
            )
        with Session(engine) as session:
            first_renewal = session.scalar(
                select(OperationLease.renewed_at).where(
                    OperationLease.scope == "postgres_heartbeat"
                )
            )
        assert first_renewal is not None
        guard = RenewableOperationLeaseGuard(
            handles,
            lambda: Session(engine),
            "integration-secret",
            ttl=timedelta(seconds=4),
            heartbeat=timedelta(seconds=1),
        )
        renewed_at = first_renewal
        deadline = monotonic() + 5
        while renewed_at <= first_renewal and monotonic() < deadline:
            sleep(0.1)
            guard.ensure_owned()
            with Session(engine) as session:
                renewed_at = session.scalar(
                    select(OperationLease.renewed_at).where(
                        OperationLease.scope == "postgres_heartbeat"
                    )
                )
            assert renewed_at is not None
        guard.close()
        assert renewed_at > first_renewal
        with Session(engine) as session:
            heartbeat_lease = session.scalar(
                select(OperationLease).where(
                    OperationLease.scope == "postgres_heartbeat"
                )
            )
            assert heartbeat_lease is not None
            assert heartbeat_lease.released_at is not None

        # Two growth transactions that individually fit but jointly exceed the
        # entitlement must serialize at the quota boundary; exactly one wins.
        quota_user_id = uuid4()
        quota_library_id = uuid4()
        with Session(engine) as session:
            session.add_all(
                [
                    User(
                        id=quota_user_id,
                        email="quota-race@example.test",
                        username="quota_race",
                        password_hash="not-a-real-hash",
                        state="active",
                    ),
                    Library(
                        id=quota_library_id,
                        name="Quota race",
                        slug="postgres-quota-race",
                    ),
                ]
            )
            session.flush()
            session.add(
                LibraryMembership(
                    library_id=quota_library_id,
                    user_id=quota_user_id,
                    role="OWNER",
                )
            )
            session.commit()
            StorageService(StorageRepository(session)).rebuild_owned_library_usage()
            probe = Book(
                library_id=quota_library_id,
                title="Concurrent quota 0",
                author="Author",
            )
            session.add(probe)
            session.flush()
            one_book_limit = calculate_library_logical_bytes(session, quota_library_id)
            session.rollback()
            entitlement = session.get(AccountStorageEntitlement, quota_user_id)
            assert entitlement is not None
            entitlement.limit_bytes = one_book_limit
            session.commit()

        def grow_quota_library(number: int) -> bool:
            with Session(engine) as concurrent_session:
                repository = BookRepository(concurrent_session)
                repository.add(
                    Book(
                        library_id=quota_library_id,
                        title=f"Concurrent quota {number}",
                        author="Author",
                    )
                )
                try:
                    repository.commit()
                except InsufficientSharedCapacity:
                    return False
                return True

        with ThreadPoolExecutor(max_workers=2) as executor:
            quota_results = list(executor.map(grow_quota_library, (1, 2)))
        assert sorted(quota_results) == [False, True]
        with Session(engine) as session:
            assert session.scalar(
                select(func.count()).select_from(Book).where(
                    Book.library_id == quota_library_id
                )
            ) == 1
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM libraries WHERE id = :id"),
                {"id": quota_library_id},
            )
            connection.execute(
                text("DELETE FROM users WHERE id = :id"),
                {"id": quota_user_id},
            )

        # Phase 6 history must make a destructive 0014 downgrade fail. Once
        # the synthetic row is removed, prove 0014 and 0013 are independently
        # reversible and then restore head.
        with Session(engine) as session:
            session.add(
                Loan(
                    library_id=first_library_id,
                    book_id=first_book_id,
                    state="ACTIVE",
                    loaned_to="Migration test borrower",
                )
            )
            session.commit()
        with pytest.raises(RuntimeError, match="must be preserved"):
            command.downgrade(alembic, "0013_remove_shared_goodreads")
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM loans"))
        command.downgrade(alembic, "0013_remove_shared_goodreads")
        assert "loans" not in set(inspect(engine).get_table_names())
        command.upgrade(alembic, "head")
        assert "loans" in set(inspect(engine).get_table_names())

        # Prove 0013 is independently reversible, restoring only the empty
        # compatibility column before removing it again.
        command.downgrade(alembic, "0012_personal_readings")
        assert "goodreads_url" in {
            column["name"] for column in inspect(engine).get_columns("books")
        }
        command.upgrade(alembic, "head")
        assert "goodreads_url" not in {
            column["name"] for column in inspect(engine).get_columns("books")
        }

        # Prove 0012 is independently reversible without altering Phase 4.
        command.downgrade(alembic, "0011_explicit_shelves")
        phase_eleven_tables = set(inspect(engine).get_table_names())
        assert {"reading_sessions", "personal_book_records"}.isdisjoint(
            phase_eleven_tables
        )
        assert {"books", "visual_shelf_layouts"} <= phase_eleven_tables
        command.upgrade(alembic, "head")
        assert {"reading_sessions", "personal_book_records"} <= set(
            inspect(engine).get_table_names()
        )

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
        # Current ORM models include columns added after 0002; inspect the
        # historical schema with SQL rather than mapping the modern User.
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM users")) == 2
            states = connection.execute(text("SELECT state FROM users")).scalars()
            assert sorted(states) == ["active", "invited"]

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

