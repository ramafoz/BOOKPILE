from datetime import timedelta
from uuid import UUID

from ..config import Settings
from .rate_limits import RateLimiter, RateLimitPolicy


class CostlyOperationLimiter:
    def __init__(self, rate_limiter: RateLimiter, settings: Settings) -> None:
        self._rate_limiter = rate_limiter
        self._settings = settings

    def check_import_preflight(self, *, user_id: UUID, library_id: UUID) -> None:
        self._check_import("import_preflight", user_id, library_id)

    def check_import_consolidation(
        self, *, user_id: UUID, library_id: UUID
    ) -> None:
        self._check_import("import_consolidation", user_id, library_id)

    def check_export(self, *, user_id: UUID, library_id: UUID) -> None:
        self._check(
            operation="portable_export",
            user_id=user_id,
            library_id=library_id,
            user_attempts=self._settings.export_attempts_per_user_per_hour,
            library_attempts=self._settings.export_attempts_per_library_per_hour,
        )

    def _check_import(
        self, operation: str, user_id: UUID, library_id: UUID
    ) -> None:
        self._check(
            operation=operation,
            user_id=user_id,
            library_id=library_id,
            user_attempts=self._settings.import_attempts_per_user_per_hour,
            library_attempts=self._settings.import_attempts_per_library_per_hour,
        )

    def _check(
        self,
        *,
        operation: str,
        user_id: UUID,
        library_id: UUID,
        user_attempts: int,
        library_attempts: int,
    ) -> None:
        mode = self._settings.defensive_limit_mode
        window = timedelta(hours=1)
        self._rate_limiter.apply(
            RateLimitPolicy(f"{operation}_user", user_attempts, window),
            key=str(user_id),
            mode=mode,
        )
        self._rate_limiter.apply(
            RateLimitPolicy(f"{operation}_library", library_attempts, window),
            key=str(library_id),
            mode=mode,
        )
