from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, HTTPException, status
from fastapi.background import BackgroundTasks
from fastapi.responses import FileResponse

from ...services.portable_exports import PortableExportNotFound
from ..dependencies import CurrentAuthDependency, PortableExportServiceDependency


router = APIRouter(tags=["exports"])


def remove_export(path: Path) -> None:
    path.unlink(missing_ok=True)


@router.get("/libraries/{library_id}/exports/portable")
def download_portable_export(
    library_id: UUID,
    background: BackgroundTasks,
    service: PortableExportServiceDependency,
    context: CurrentAuthDependency,
) -> FileResponse:
    try:
        prepared = service.create(library_id=library_id, actor_user_id=context.user_id)
    except PortableExportNotFound as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Library not found") from exc
    background.add_task(remove_export, prepared.path)
    return FileResponse(
        prepared.path,
        filename=prepared.download_name,
        media_type="application/zip",
        background=background,
    )
