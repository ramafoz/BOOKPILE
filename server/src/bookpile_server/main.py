from fastapi import FastAPI, Request

from .api.routes.catalogue import router as catalogue_router
from .api.routes.auth import router as auth_router
from .api.routes.libraries import router as libraries_router
from .api.routes.physical_library import router as physical_library_router


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

