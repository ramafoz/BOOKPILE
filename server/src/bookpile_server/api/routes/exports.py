from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask

from ...services.portable_exports import PortableExportNotFound
from ...services.costly_operation_leases import (
    CostlyOperationLeaseDecisionUnavailableError,
    CostlyOperationLeaseUnavailableError,
)
from ...services.rate_limits import (
    RateLimitDecisionUnavailableError,
    RateLimitExceededError,
)
from ..dependencies import (
    CostlyOperationLimiterDependency,
    CostlyOperationLeaseServiceDependency,
    CurrentAuthDependency,
    PortableExportServiceDependency,
)
from ..leased_file_response import LeaseProtectedFileResponse


router = APIRouter(tags=["exports"])


def remove_export(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/libraries/{library_id}/exports/portable")
def download_portable_export(
    library_id: UUID,
    service: PortableExportServiceDependency,
    limiter: CostlyOperationLimiterDependency,
    leases: CostlyOperationLeaseServiceDependency,
    context: CurrentAuthDependency,
) -> FileResponse:
    guard = None
    try:
        service.require_owner(
            library_id=library_id, actor_user_id=context.user_id
        )
        limiter.check_export(user_id=context.user_id, library_id=library_id)
        guard = leases.acquire_export(
            user_id=context.user_id, library_id=library_id
        )
        prepared = service.create(library_id=library_id, actor_user_id=context.user_id)
        if guard is not None:
            guard.ensure_owned()
    except PortableExportNotFound as exc:
        if guard is not None:
            guard.close()
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
    except CostlyOperationLeaseUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A portable export is already active.",
        ) from exc
    except CostlyOperationLeaseDecisionUnavailableError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Operation coordination is temporarily unavailable.",
        ) from exc
    except Exception:
        if guard is not None:
            guard.close()
        raise
    if guard is not None:
        return LeaseProtectedFileResponse(
            prepared.path,
            guard,
            filename=prepared.download_name,
            media_type="application/zip",
        )
    return FileResponse(
        prepared.path,
        filename=prepared.download_name,
        media_type="application/zip",
        background=BackgroundTask(remove_export, prepared.path),
    )
