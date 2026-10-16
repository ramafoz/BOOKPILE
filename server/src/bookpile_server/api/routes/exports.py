from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse

from ...services.portable_exports import PortableExportNotFound
from ...services.rate_limits import (
    RateLimitDecisionUnavailableError,
    RateLimitExceededError,
)
from ..dependencies import (
    CostlyOperationLimiterDependency,
    CurrentAuthDependency,
    PortableExportServiceDependency,
)


router = APIRouter(tags=["exports"])


def remove_export(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/libraries/{library_id}/exports/portable")
def download_portable_export(
    library_id: UUID,
    background: BackgroundTasks,
    service: PortableExportServiceDependency,
    limiter: CostlyOperationLimiterDependency,
    context: CurrentAuthDependency,
) -> FileResponse:
    try:
        service.require_owner(
            library_id=library_id, actor_user_id=context.user_id
        )
        limiter.check_export(user_id=context.user_id, library_id=library_id)
        prepared = service.create(library_id=library_id, actor_user_id=context.user_id)
    except PortableExportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library not found") from exc
    except RateLimitExceededError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests. Try again later.",
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except RateLimitDecisionUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Request limiting is temporarily unavailable.",
        ) from exc
    background.add_task(remove_export, prepared.path)
    return FileResponse(
        prepared.path,
        filename=prepared.download_name,
        media_type="application/zip",
        background=background,
    )
