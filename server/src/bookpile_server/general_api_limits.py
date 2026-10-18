from collections.abc import Awaitable, Callable
from datetime import timedelta
from ipaddress import ip_address
from typing import Any

from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from .config import Settings
from .repositories.rate_limits import RateLimitRepository
from .services.rate_limits import (
    RateLimitDecisionUnavailableError,
    RateLimitExceededError,
    RateLimiter,
    RateLimitPolicy,
)


ASGIApp = Callable[..., Awaitable[None]]
SessionFactory = Callable[[], Session]


class GeneralApiRateLimitMiddleware:
    """Apply one shared, privacy-safe client-IP ceiling to API traffic."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        settings: Settings,
        session_factory: SessionFactory,
    ) -> None:
        self.app = app
        self.settings = settings
        self.session_factory = session_factory
        self.policy = RateLimitPolicy(
            "general_api_ip",
            settings.general_api_attempts_per_ip_per_minute,
            timedelta(minutes=1),
        )

    async def __call__(self, scope, receive, send) -> None:
        if not self._should_count(scope):
            await self.app(scope, receive, send)
            return

        try:
            client_ip = self._client_ip(scope)
            await run_in_threadpool(self._check, client_ip)
        except RateLimitExceededError as exc:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Try again later."},
                headers={"Retry-After": str(exc.retry_after)},
            )
            await response(scope, receive, send)
            return
        except (RateLimitDecisionUnavailableError, ValueError):
            response = JSONResponse(
                status_code=503,
                content={"detail": "Request limiting is temporarily unavailable."},
            )
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)

    def _should_count(self, scope: dict[str, Any]) -> bool:
        return (
            self.settings.general_api_limit_mode != "off"
            and scope.get("type") == "http"
            and str(scope.get("path", "")).startswith("/api/")
        )

    @staticmethod
    def _client_ip(scope: dict[str, Any]) -> str:
        client = scope.get("client")
        if not isinstance(client, (tuple, list)) or not client:
            raise ValueError("Missing validated client address")
        address = ip_address(str(client[0]))
        mapped = getattr(address, "ipv4_mapped", None)
        return str(mapped or address)

    def _check(self, client_ip: str) -> None:
        with self.session_factory() as session:
            RateLimiter(
                RateLimitRepository(session),
                self.settings.rate_limit_key_secret,
                self.settings.deployment_revision,
            ).apply(
                self.policy,
                key=client_ip,
                mode=self.settings.general_api_limit_mode,
            )
