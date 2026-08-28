from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


SERVER_DIRECTORY = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Process configuration supplied by the hosting environment."""

    model_config = SettingsConfigDict(
        env_prefix="BOOKPILE_SERVER_",
        env_file=SERVER_DIRECTORY / ".env",
        extra="ignore",
    )

    environment: Literal["development", "test", "staging", "production"] = (
        "development"
    )
    database_url: str = Field(
        default="postgresql+psycopg://bookpile:bookpile-dev@localhost:5432/bookpile"
    )
    sql_echo: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
