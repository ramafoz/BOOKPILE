from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .api.routes.catalogue import router as catalogue_router
from .api.routes.auth import router as auth_router
from .api.routes.libraries import router as libraries_router
from .api.routes.loans import overview_router as loans_overview_router, router as loans_router
from .api.routes.physical_library import router as physical_library_router
from .api.routes.readings import overview_router as readings_overview_router, router as readings_router
from .api.routes.profiles import router as profiles_router
from .services.storage_domain import InsufficientSharedCapacity


def create_app() -> FastAPI:
    app = FastAPI(
        title="BOOKPILE Server",
        version="0.1.0-dev",
        description="Multi-user foundation with first-party authentication.",
    )
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(catalogue_router, prefix="/api/v1")
    app.include_router(libraries_router, prefix="/api/v1")
    app.include_router(physical_library_router, prefix="/api/v1")
    app.include_router(readings_router, prefix="/api/v1")
    app.include_router(readings_overview_router, prefix="/api/v1")
    app.include_router(loans_router, prefix="/api/v1")
    app.include_router(loans_overview_router, prefix="/api/v1")
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
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/v1/auth") or request.url.path.endswith("/cover"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "edition": "server"}

    return app


app = create_app()

