from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from bookpile_server.database import get_session
from bookpile_server.api.dependencies import get_email_sender
from bookpile_server.email_delivery import OutgoingEmail
from bookpile_server.main import create_app
from bookpile_server.models import Base


class RecordingEmailSender:
    def __init__(self) -> None:
        self.emails: list[OutgoingEmail] = []

    def send(self, email: OutgoingEmail) -> None:
        self.emails.append(email)


@pytest.fixture
def email_sender() -> RecordingEmailSender:
    return RecordingEmailSender()


@pytest.fixture
def session() -> Generator[Session, None, None]:
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.connect() as connection:
        connection.exec_driver_sql("PRAGMA foreign_keys = ON")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as database_session:
        yield database_session
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def client(
    session: Session, email_sender: RecordingEmailSender
) -> Generator[TestClient, None, None]:
    app = create_app()

    def override_session() -> Generator[Session, None, None]:
        yield session

    app.dependency_overrides[get_session] = override_session
    app.dependency_overrides[get_email_sender] = lambda: email_sender
    with TestClient(app) as test_client:
        yield test_client

