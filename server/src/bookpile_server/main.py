from fastapi import FastAPI

from .api.routes.catalogue import router as catalogue_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="BOOKPILE Server",
        version="0.1.0-dev",
        description="Multi-user foundation. Authentication is not implemented yet.",
    )
    app.include_router(catalogue_router, prefix="/api/v1")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "edition": "server"}

    return app


app = create_app()

