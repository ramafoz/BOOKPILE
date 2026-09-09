from uuid import UUID

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status

from ...imports.local_zip import LocalImportValidationError
from ...schemas import LocalImportJobResponse, LocalImportPreflightResponse
from ...services.local_imports import (
    LocalImportOwnerRequired,
    LocalImportReadingOwnerInvalid,
    LocalImportService,
    LocalImportUploadTooLarge,
)
from ..dependencies import CsrfDependency, CurrentAuthDependency, LocalImportServiceDependency


router = APIRouter(tags=["imports"])


def response_for(job) -> LocalImportJobResponse:
    return LocalImportJobResponse(
        import_id=job.id,
        state=job.state,
        adapter=job.adapter,
        backup_format_version=job.backup_format_version,
        local_schema_version=job.local_schema_version,
        source_created_at=job.source_created_at,
        reading_owner_user_id=job.reading_owner_user_id,
        counts=job.source_counts,
        estimated_logical_bytes=job.estimated_logical_bytes,
        capacity_available=job.capacity_available,
        expires_at=job.expires_at,
        warnings=job.warnings,
    )


@router.post(
    "/libraries/{library_id}/imports/local/preflight",
    response_model=LocalImportPreflightResponse,
    status_code=status.HTTP_201_CREATED,
)
def preflight_local_import(
    library_id: UUID,
    service: LocalImportServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
    reading_owner_user_id: UUID = Form(...),
    backup: UploadFile = File(...),
) -> LocalImportPreflightResponse:
    try:
        job = service.preflight(
            library_id=library_id,
            actor_user_id=context.user_id,
            reading_owner_user_id=reading_owner_user_id,
            upload=backup.file,
        )
    except LocalImportUploadTooLarge as exc:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=str(exc)) from exc
    except (LocalImportOwnerRequired, LocalImportReadingOwnerInvalid) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library or selected Owner not found") from exc
    except LocalImportValidationError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    finally:
        backup.file.close()
    return response_for(job)


@router.get(
    "/libraries/{library_id}/imports/{import_id}",
    response_model=LocalImportJobResponse,
)
def get_import_job(
    library_id: UUID,
    import_id: UUID,
    service: LocalImportServiceDependency,
    context: CurrentAuthDependency,
) -> LocalImportJobResponse:
    try:
        return response_for(
            service.find_ready(
                import_id=import_id,
                library_id=library_id,
                actor_user_id=context.user_id,
            )
        )
    except LocalImportOwnerRequired as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found") from exc


@router.delete(
    "/libraries/{library_id}/imports/{import_id}",
    response_model=LocalImportJobResponse,
)
def cancel_import_job(
    library_id: UUID,
    import_id: UUID,
    service: LocalImportServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> LocalImportJobResponse:
    try:
        return response_for(
            service.cancel(
                import_id=import_id,
                library_id=library_id,
                actor_user_id=context.user_id,
            )
        )
    except LocalImportOwnerRequired as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import not found") from exc
