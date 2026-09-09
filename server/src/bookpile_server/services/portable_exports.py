from dataclasses import dataclass
from pathlib import Path
import re
from uuid import UUID, uuid4

from ..cover_storage import CoverStorage
from ..exports.server_library import create_server_library_export
from ..repositories.imports import LocalImportRepository


class PortableExportNotFound(Exception):
    pass


@dataclass(frozen=True)
class PreparedPortableExport:
    path: Path
    download_name: str


class PortableExportService:
    def __init__(
        self,
        repository: LocalImportRepository,
        storage: CoverStorage,
        export_root: Path,
    ) -> None:
        self.repository = repository
        self.storage = storage
        self.export_root = export_root.resolve()

    def create(self, *, library_id: UUID, actor_user_id: UUID) -> PreparedPortableExport:
        membership = self.repository.owner_membership(library_id, actor_user_id)
        if membership is None:
            raise PortableExportNotFound
        token = uuid4().hex
        path = self.export_root / f"{token}.zip"
        create_server_library_export(
            session=self.repository.session,
            storage=self.storage,
            library_id=library_id,
            destination=path,
        )
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "-", membership.library.name).strip("-.") or "library"
        return PreparedPortableExport(path, f"BOOKPILE-{safe_name}.zip")
