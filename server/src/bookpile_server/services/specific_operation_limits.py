from datetime import timedelta
from uuid import UUID

from ..config import Settings
from .rate_limits import RateLimiter, RateLimitPolicy


class SpecificOperationRateLimiter:
    """Shared limits for individually expensive interactive operations."""

    def __init__(self, rate_limiter: RateLimiter, settings: Settings) -> None:
        self._rate_limiter = rate_limiter
        self._settings = settings

    def check_bibliographic_user(self, user_id: UUID) -> None:
        self._rate_limiter.enforce(
            RateLimitPolicy(
                "bibliographic_lookup",
                self._settings.bibliographic_lookup_attempts_per_user_per_hour,
                timedelta(hours=1),
            ),
            key=str(user_id),
            ip_address=None,
        )

    def check_bibliographic_ip(
        self,
        client_ip: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "bibliographic_lookup_ip",
                self._settings.bibliographic_lookup_attempts_per_ip_per_hour,
                timedelta(hours=1),
            ),
            key=client_ip,
            mode=self._settings.bibliographic_lookup_limit_mode,
            correlation_id=correlation_id,
        )

    def check_bibliographic_library(
        self,
        library_id: UUID,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "bibliographic_lookup_library",
                self._settings.bibliographic_lookup_attempts_per_library_per_hour,
                timedelta(hours=1),
            ),
            key=str(library_id),
            mode=self._settings.bibliographic_lookup_limit_mode,
            correlation_id=correlation_id,
        )

    def check_cover_user(self, user_id: UUID) -> None:
        self._rate_limiter.enforce(
            RateLimitPolicy(
                "cover_upload",
                self._settings.cover_upload_attempts_per_hour,
                timedelta(hours=1),
            ),
            key=str(user_id),
            ip_address=None,
        )

    def check_cover_library(
        self,
        library_id: UUID,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "cover_upload_library",
                self._settings.cover_upload_attempts_per_library_per_hour,
                timedelta(hours=1),
            ),
            key=str(library_id),
            mode=self._settings.cover_upload_library_limit_mode,
            correlation_id=correlation_id,
        )

    def check_rearrangement_user(
        self,
        user_id: UUID,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "rearrangement_user",
                self._settings.rearrangement_attempts_per_user_per_minute,
                timedelta(minutes=1),
            ),
            key=str(user_id),
            mode=self._settings.rearrangement_limit_mode,
            correlation_id=correlation_id,
        )

    def check_rearrangement_library(
        self,
        library_id: UUID,
        *,
        correlation_id: str | None = None,
    ) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "rearrangement_library",
                self._settings.rearrangement_attempts_per_library_per_minute,
                timedelta(minutes=1),
            ),
            key=str(library_id),
            mode=self._settings.rearrangement_limit_mode,
            correlation_id=correlation_id,
        )
