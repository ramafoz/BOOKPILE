from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


SERVER_DIRECTORY = Path(__file__).resolve().parents[2]
DEVELOPMENT_RATE_LIMIT_SECRET = "bookpile-development-rate-limit-secret"


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
        default="postgresql+psycopg://bookpile:bookpile-dev@127.0.0.1:5432/bookpile"
    )
    sql_echo: bool = False
    session_cookie_name: str = "bookpile_session"
    csrf_cookie_name: str = "bookpile_csrf"
    session_cookie_secure: bool = False
    public_base_url: str = "http://127.0.0.1:5173"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_from_email: str = "BOOKPILE <noreply@bookpile.local>"
    rate_limit_key_secret: str = DEVELOPMENT_RATE_LIMIT_SECRET
    private_object_root: Path = SERVER_DIRECTORY.parent / ".bookpile-runtime" / "private-objects"
    cover_max_upload_bytes: int = 12 * 1024 * 1024
    cover_max_pixels: int = 40_000_000
    cover_max_width: int = 900
    cover_max_height: int = 1400
    cover_webp_quality: int = 82
    cover_upload_attempts_per_hour: int = 30

    @model_validator(mode="after")
    def require_production_security_settings(self) -> "Settings":
        if self.environment == "production":
            if self.rate_limit_key_secret == DEVELOPMENT_RATE_LIMIT_SECRET:
                raise ValueError(
                    "Production requires a private BOOKPILE_SERVER_RATE_LIMIT_KEY_SECRET"
                )
            if not self.session_cookie_secure:
                raise ValueError(
                    "Production requires BOOKPILE_SERVER_SESSION_COOKIE_SECURE=true"
                )
            if not self.public_base_url.startswith("https://"):
                raise ValueError(
                    "Production requires an HTTPS BOOKPILE_SERVER_PUBLIC_BASE_URL"
                )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
