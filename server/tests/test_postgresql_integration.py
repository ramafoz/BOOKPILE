"""Opt-in PostgreSQL gate for Phase 1.

Set BOOKPILE_SERVER_TEST_DATABASE_URL to a disposable database whose name ends
in `_test`. The safety suffix prevents this test from targeting a normal or
production database accidentally.
"""
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from bookpile_server.database import get_session
from bookpile_server.main import create_app
from bookpile_server.models import (
    AccountInvitation,
    AccountActionToken,
    Book,
    Library,
    RateLimitBucket,
    SecurityEvent,
    User,
    UserSession,
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
        } <= set(inspect(engine).get_table_names())
        with Session(engine) as session:
            first = Library(name="First", slug="postgres-first")
            second = Library(name="Second", slug="postgres-second")
            session.add_all([first, second])
            session.flush()
            session.add_all(
                [
                    Book(library_id=first.id, title="One", author="Author A"),
                    Book(library_id=second.id, title="Two", author="Author B"),
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
            session.add(
                UserSession(
                    user_id=user.id,
                    token_hash="a" * 64,
                    csrf_token_hash="b" * 64,
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
                response = client.get(
                    f"/api/v1/libraries/{first.id}/catalogue",
                    params={"search": "one"},
                )
            assert response.status_code == 200
            assert response.json()["total"] == 1
            assert [book["title"] for book in response.json()["books"]] == [
                "One"
            ]
            assert "Two" not in response.text

            locked_action = AccountActionRepository(session).get_token_for_update(
                token_hash="d" * 64,
                purpose="email_verification",
            )
            assert locked_action is not None
            assert locked_action.user.id == user.id

            invitation_result = AccountInvitationService(
                AccountInvitationRepository(session)
            ).create()

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
        with Session(engine) as session:
            assert session.query(Library).count() == 2
            assert session.query(Book).count() == 2
    finally:
        command.downgrade(alembic, "base")
        remaining_tables = set(inspect(engine).get_table_names())
        assert remaining_tables <= {"alembic_version"}
        engine.dispose()

