from datetime import timedelta
from uuid import UUID

from ..config import Settings
from .rate_limits import RateLimiter, RateLimitPolicy


class MutationRateLimiter:
    """Apply independently switchable mutation ceilings."""

    def __init__(self, rate_limiter: RateLimiter, settings: Settings) -> None:
        self._rate_limiter = rate_limiter
        self._settings = settings
        self._window = timedelta(minutes=15)

    def check_user(self, user_id: UUID) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "mutation_user",
                self._settings.mutation_attempts_per_user_per_15_minutes,
                self._window,
            ),
            key=str(user_id),
            mode=self._settings.mutation_user_limit_mode,
        )

    def check_library(self, library_id: UUID) -> None:
        self._rate_limiter.apply(
            RateLimitPolicy(
                "mutation_library",
                self._settings.mutation_attempts_per_library_per_15_minutes,
                self._window,
            ),
            key=str(library_id),
            mode=self._settings.mutation_library_limit_mode,
        )
