from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from .config import get_settings


def build_engine(database_url: str, *, echo: bool = False) -> Engine:
    return create_engine(database_url, echo=echo, pool_pre_ping=True)


settings = get_settings()
engine = build_engine(settings.database_url, echo=settings.sql_echo)
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


def get_session() -> Generator[Session, None, None]:
    """Provide one transaction boundary per request."""

    with SessionFactory() as session:
        yield session

