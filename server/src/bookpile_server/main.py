import json
import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text

from .api.routes.catalogue import router as catalogue_router
from .api.routes.auth import router as auth_router
from .api.routes.libraries import router as libraries_router
from .api.routes.loans import overview_router as loans_overview_router, router as loans_router
from .api.routes.imports import router as imports_router
from .api.routes.exports import router as exports_router
from .api.routes.physical_library import router as physical_library_router
from .api.routes.readings import overview_router as readings_overview_router, router as readings_router
from .api.routes.profiles import router as profiles_router
from .services.storage_domain import InsufficientSharedCapacity
from .api.dependencies import PrivateObjectStorageDependency, SessionDependency
from .config import get_settings


request_logger = logging.getLogger("bookpile.requests")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="BOOKPILE Server",
        version="0.1.0-dev",
        description="Multi-user foundation with first-party authentication.",
        docs_url="/docs" if settings.api_docs_enabled else None,
        redoc_url="/redoc" if settings.api_docs_enabled else None,
        openapi_url="/openapi.json" if settings.api_docs_enabled else None,
    )
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.allowed_host_values)
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(catalogue_router, prefix="/api/v1")
    app.include_router(libraries_router, prefix="/api/v1")
    app.include_router(physical_library_router, prefix="/api/v1")
    app.include_router(readings_router, prefix="/api/v1")
    app.include_router(readings_overview_router, prefix="/api/v1")
    app.include_router(loans_router, prefix="/api/v1")
    app.include_router(loans_overview_router, prefix="/api/v1")
    app.include_router(imports_router, prefix="/api/v1")
    app.include_router(exports_router, prefix="/api/v1")
    app.include_router(profiles_router, prefix="/api/v1")

    @app.exception_handler(InsufficientSharedCapacity)
    async def storage_capacity_error(
        _request: Request, _exc: InsufficientSharedCapacity
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"detail": "Shared storage capacity is insufficient."},
        )

    @app.middleware("http")
    async def add_security_headers(request: Request, call_next):
        request_id = uuid4().hex
        started = perf_counter()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
        finally:
            route = request.scope.get("route")
            route_path = getattr(route, "path", "unmatched")
            request_logger.info(json.dumps({
                "event": "http_request",
                "request_id": request_id,
                "method": request.method,
                "route": route_path,
                "status": status_code,
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "deployment_revision": settings.deployment_revision,
            }, separators=(",", ":")))
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(self), microphone=(), geolocation=()"
        if settings.is_hosted:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        if request.url.path.startswith("/api/v1/auth") or request.url.path.endswith("/cover"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health", include_in_schema=False)
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "edition": "server",
            "revision": settings.deployment_revision,
        }

    @app.get("/health/live", include_in_schema=False)
    def liveness() -> dict[str, str]:
        return {"status": "alive", "revision": settings.deployment_revision}

    @app.get("/health/ready", include_in_schema=False)
    def readiness(
        session: SessionDependency,
        object_storage: PrivateObjectStorageDependency,
    ):
        checks: dict[str, str] = {}
        try:
            session.execute(text("SELECT 1"))
            checks["database"] = "ready"
        except Exception:
            checks["database"] = "unavailable"
        try:
            object_storage.check_ready()
            checks["private_objects"] = "ready"
        except Exception:
            checks["private_objects"] = "unavailable"
        ready = all(value == "ready" for value in checks.values())
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ready" if ready else "unavailable",
                "revision": settings.deployment_revision,
                "checks": checks,
            },
        )

    return app


app = create_app()

