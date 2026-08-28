from fastapi import FastAPI

from .api.routes.catalogue import router as catalogue_router
from .api.routes.auth import router as auth_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="BOOKPILE Server",
        version="0.1.0-dev",
        description="Multi-user foundation with first-party authentication.",
    )
    app.include_router(auth_router, prefix="/api/v1")
    app.include_router(catalogue_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "edition": "server"}

    return app


app = create_app()

