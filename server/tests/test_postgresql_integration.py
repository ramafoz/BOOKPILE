"""Opt-in PostgreSQL gate for Phase 1.

Set BOOKPILE_SERVER_TEST_DATABASE_URL to a disposable database whose name ends
in `_test`. The safety suffix prevents this test from targeting a normal or
production database accidentally.
"""
import os
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from fastapi.testclient import TestClient

from bookpile_server.database import get_session
from bookpile_server.main import create_app
from bookpile_server.models import Book, Library
from bookpile_server.repositories.books import BookRepository


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
    finally:
        command.downgrade(alembic, "base")
        remaining_tables = set(inspect(engine).get_table_names())
        assert remaining_tables <= {"alembic_version"}
        engine.dispose()

