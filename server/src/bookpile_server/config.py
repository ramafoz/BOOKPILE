from functools import lru_cache
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

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
    deployment_revision: str = "development"
    allowed_hosts: str = ""
    api_docs_enabled: bool = True
    database_pool_size: int = Field(default=5, ge=1, le=50)
    database_max_overflow: int = Field(default=5, ge=0, le=100)
    database_pool_recycle_seconds: int = Field(default=1800, ge=60, le=86400)
    session_cookie_name: str = "bookpile_session"
    csrf_cookie_name: str = "bookpile_csrf"
    session_cookie_secure: bool = False
    public_base_url: str = "http://127.0.0.1:5174"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_from_email: str = "BOOKPILE <noreply@bookpile.local>"
    rate_limit_key_secret: str = DEVELOPMENT_RATE_LIMIT_SECRET
    private_object_root: Path = SERVER_DIRECTORY.parent / ".bookpile-runtime" / "private-objects"
    import_staging_root: Path = SERVER_DIRECTORY.parent / ".bookpile-runtime" / "import-staging"
    import_staging_ttl_minutes: int = 30
    export_staging_root: Path = SERVER_DIRECTORY.parent / ".bookpile-runtime" / "export-staging"
    cover_max_upload_bytes: int = 12 * 1024 * 1024
    cover_max_pixels: int = 40_000_000
    cover_max_width: int = 900
    cover_max_height: int = 1400
    cover_webp_quality: int = 82
    cover_upload_attempts_per_hour: int = 30

    @property
    def is_hosted(self) -> bool:
        return self.environment in {"staging", "production"}

    @property
    def public_origin(self) -> str:
        parsed = urlsplit(self.public_base_url)
        return f"{parsed.scheme}://{parsed.netloc}"

    @property
    def allowed_host_values(self) -> list[str]:
        configured = [item.strip() for item in self.allowed_hosts.split(",") if item.strip()]
        if configured:
            return configured
        hostname = urlsplit(self.public_base_url).hostname
        return [hostname] if self.is_hosted and hostname else ["127.0.0.1", "localhost", "testserver"]

    @model_validator(mode="after")
    def require_production_security_settings(self) -> "Settings":
        if self.is_hosted:
            if self.rate_limit_key_secret == DEVELOPMENT_RATE_LIMIT_SECRET:
                raise ValueError(
                    "Hosted environments require a private BOOKPILE_SERVER_RATE_LIMIT_KEY_SECRET"
                )
            if len(self.rate_limit_key_secret) < 32:
                raise ValueError("The hosted rate-limit secret must contain at least 32 characters")
            if not self.session_cookie_secure:
                raise ValueError(
                    "Hosted environments require BOOKPILE_SERVER_SESSION_COOKIE_SECURE=true"
                )
            parsed = urlsplit(self.public_base_url)
            if (
                parsed.scheme != "https"
                or not parsed.hostname
                or parsed.username
                or parsed.password
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError(
                    "Hosted environments require one HTTPS BOOKPILE_SERVER_PUBLIC_BASE_URL origin"
                )
            if parsed.path not in {"", "/"}:
                raise ValueError("The hosted public URL must not contain an application path")
            if self.api_docs_enabled:
                raise ValueError("Hosted API documentation must be disabled")
            if self.deployment_revision.strip().lower() in {"", "development", "unknown"}:
                raise ValueError("Hosted environments require an explicit deployment revision")
            if not self.database_url.startswith(("postgresql://", "postgresql+psycopg://")):
                raise ValueError("Hosted environments require PostgreSQL")
            if "bookpile-dev" in self.database_url:
                raise ValueError("Hosted environments cannot use the development database credential")
            hosts = self.allowed_host_values
            if "*" in hosts:
                raise ValueError("Hosted environments cannot trust every Host header")
            if parsed.hostname not in hosts:
                raise ValueError("Hosted allowed hosts must include the public hostname")
            if any("://" in host or "/" in host for host in hosts):
                raise ValueError("Allowed hosts contain hostnames only, without scheme or path")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
