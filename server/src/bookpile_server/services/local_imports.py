from datetime import UTC, datetime, timedelta
from pathlib import Path
import shutil
from hashlib import sha256
from typing import BinaryIO
from uuid import UUID, uuid4

from ..imports.local_zip import (
    LocalArchiveLimits,
    LocalImportValidationError,
    adapt_local_v8,
    inspect_local_backup,
)
from ..models import LibraryImportJob
from ..cover_storage import CoverStorage
from ..config import Settings
from ..cover_images import InvalidCoverImage, process_cover_image
from ..imports.consolidation import LocalImportConflict, consolidate_local_v8
from ..repositories.imports import LocalImportRepository
from .storage_domain import logical_collection_bytes
from .storage import StorageService


class LocalImportOwnerRequired(Exception):
    pass


class LocalImportReadingOwnerInvalid(Exception):
    pass


class LocalImportUploadTooLarge(LocalImportValidationError):
    pass


class LocalImportStateConflict(Exception):
    pass


class LocalImportService:
    def __init__(
        self,
        repository: LocalImportRepository,
        staging_root: Path,
        *,
        ttl_minutes: int = 30,
        limits: LocalArchiveLimits | None = None,
        storage_service: StorageService | None = None,
        object_storage: CoverStorage | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.repository = repository
        self.staging_root = staging_root.resolve()
        self.ttl_minutes = ttl_minutes
        self.limits = limits or LocalArchiveLimits()
        self.storage_service = storage_service
        self.object_storage = object_storage
        self.settings = settings

    @staticmethod
    def _staging_fingerprint(directory: Path) -> str:
        digest = sha256()
        for path in sorted((item for item in directory.rglob("*") if item.is_file()), key=lambda item: item.relative_to(directory).as_posix()):
            digest.update(path.relative_to(directory).as_posix().encode("utf-8"))
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        return digest.hexdigest()

    def _processed_cover_bytes(self, extracted: Path, records, fallback: int) -> int:
        if self.settings is None:
            return fallback
        total = 0
        for book in records.books:
            filename = book["cover_filename"]
            if not filename:
                continue
            try:
                total += len(
                    process_cover_image(
                        (extracted / "covers" / str(filename)).read_bytes(),
                        self.settings,
                    ).content
                )
            except (InvalidCoverImage, OSError) as exc:
                raise LocalImportValidationError(
                    f"A Local cover cannot enter private Server storage: {filename}."
                ) from exc
        return total

    def _write_upload(self, source: BinaryIO, destination: Path) -> None:
        written = 0
        with destination.open("xb") as output:
            while chunk := source.read(1024 * 1024):
                written += len(chunk)
                if written > self.limits.max_archive_bytes:
                    raise LocalImportUploadTooLarge(
                        "Local BOOKPILE ZIP backups must be 100 MiB or smaller."
                    )
                output.write(chunk)

    def cleanup_expired(self) -> int:
        jobs = self.repository.expired_staged_jobs(datetime.now(UTC))
        for job in jobs:
            job.state = "EXPIRED"
            shutil.rmtree(self.staging_root / job.staging_key, ignore_errors=True)
        if jobs:
            self.repository.commit()
        return len(jobs)

    @staticmethod
    def _estimate(records, cover_bytes: int) -> int:
        groups = (
            ("bookcases", records.bookcases),
            ("shelves", records.shelves),
            ("containers", records.containers),
            ("books", records.books),
            ("book_contributors", records.contributors),
            ("reading_sessions", records.readings),
            ("loans", records.loans),
            ("visual_bookcase_layouts", records.bookcase_layouts),
            ("visual_outside_areas", records.outside_areas),
            ("visual_shelf_layouts", records.shelf_layouts),
            ("visual_container_layouts", records.container_layouts),
        )
        return logical_collection_bytes(
            [(kind, record) for kind, items in groups for record in items],
            object_bytes=[cover_bytes],
        )

    def _warnings(self, library_id: UUID, records, repeated: bool) -> list[dict[str, object]]:
        warnings: list[dict[str, object]] = []
        if repeated:
            warnings.append(
                {
                    "code": "REPEATED_ARCHIVE",
                    "message": "This exact Local backup was already prepared or imported into this library.",
                }
            )
        existing = self.repository.destination_books(library_id)
        isbn_values = {
            value
            for book in existing
            for value in (book.isbn_10, book.isbn_13)
            if value
        }
        titles = {(book.title.strip().casefold(), book.author.strip().casefold()) for book in existing}
        duplicate_isbn = sum(
            bool(({book.get("isbn_10"), book.get("isbn_13")} - {None}) & isbn_values)
            for book in records.books
        )
        duplicate_title = sum(
            (str(book["title"]).strip().casefold(), str(book["author"]).strip().casefold()) in titles
            for book in records.books
        )
        if duplicate_isbn:
            warnings.append({"code": "DUPLICATE_ISBN_CANDIDATES", "count": duplicate_isbn})
        if duplicate_title:
            warnings.append({"code": "DUPLICATE_TITLE_AUTHOR_CANDIDATES", "count": duplicate_title})
        return warnings

    def preflight(
        self,
        *,
        library_id: UUID,
        actor_user_id: UUID,
        reading_owner_user_id: UUID,
        upload: BinaryIO,
    ) -> LibraryImportJob:
        self.cleanup_expired()
        if self.repository.owner_membership(library_id, actor_user_id) is None:
            raise LocalImportOwnerRequired
        if self.repository.owner_membership(library_id, reading_owner_user_id) is None:
            raise LocalImportReadingOwnerInvalid

        job_id = uuid4()
        directory = self.staging_root / str(job_id)
        archive = directory / "upload.zip"
        extracted = directory / "extracted"
        directory.mkdir(parents=True, exist_ok=False)
        try:
            self._write_upload(upload, archive)
            inspection = inspect_local_backup(archive, extracted, limits=self.limits)
            records = adapt_local_v8(extracted)
            repeated = bool(self.repository.prior_jobs(library_id, inspection.archive_sha256))
            warnings = self._warnings(library_id, records, repeated)
            archive.unlink(missing_ok=True)
            processed_cover_bytes = self._processed_cover_bytes(
                extracted, records, inspection.estimated_cover_bytes
            )
            estimate = self._estimate(records, processed_cover_bytes)
            capacity_available = (
                self.storage_service.can_fit_library_growth(library_id, estimate)
                if self.storage_service is not None
                else True
            )
            if not capacity_available:
                warnings.append(
                    {
                        "code": "INSUFFICIENT_SHARED_CAPACITY",
                        "message": "The imported library data does not currently fit the Owners' shared storage capacity.",
                    }
                )
            job = LibraryImportJob(
                id=job_id,
                library_id=library_id,
                created_by_user_id=actor_user_id,
                reading_owner_user_id=reading_owner_user_id,
                state="READY",
                adapter=inspection.adapter,
                backup_format_version=inspection.backup_format_version,
                local_schema_version=inspection.local_schema_version,
                source_created_at=inspection.created_at,
                archive_sha256=inspection.archive_sha256,
                source_fingerprint=records.source_fingerprint,
                staging_sha256=self._staging_fingerprint(extracted),
                staging_key=str(job_id),
                source_counts=inspection.counts,
                warnings=warnings,
                archive_bytes=inspection.archive_bytes,
                uncompressed_bytes=inspection.uncompressed_bytes,
                estimated_logical_bytes=estimate,
                capacity_available=capacity_available,
                expires_at=datetime.now(UTC) + timedelta(minutes=self.ttl_minutes),
            )
            self.repository.add(job)
            self.repository.commit()
            return job
        except Exception:
            self.repository.rollback()
            shutil.rmtree(directory, ignore_errors=True)
            raise

    def find_ready(self, *, import_id: UUID, library_id: UUID, actor_user_id: UUID) -> LibraryImportJob:
        if self.repository.owner_membership(library_id, actor_user_id) is None:
            raise LocalImportOwnerRequired
        job = self.repository.find(import_id)
        if job is None or job.library_id != library_id:
            raise LocalImportOwnerRequired
        now = datetime.now(UTC)
        expires_at = job.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if job.state == "READY" and expires_at <= now:
            job.state = "EXPIRED"
            shutil.rmtree(self.staging_root / job.staging_key, ignore_errors=True)
            self.repository.commit()
        return job

    def cancel(self, *, import_id: UUID, library_id: UUID, actor_user_id: UUID) -> LibraryImportJob:
        job = self.find_ready(import_id=import_id, library_id=library_id, actor_user_id=actor_user_id)
        if job.state in {"READY", "FAILED", "EXPIRED"}:
            job.state = "EXPIRED"
            shutil.rmtree(self.staging_root / job.staging_key, ignore_errors=True)
            self.repository.commit()
        return job

    def consolidate(
        self,
        *,
        import_id: UUID,
        library_id: UUID,
        actor_user_id: UUID,
        allow_repeated_archive: bool,
    ) -> LibraryImportJob:
        if self.repository.owner_membership(library_id, actor_user_id) is None:
            raise LocalImportOwnerRequired
        job = self.repository.lock(import_id)
        if job is None or job.library_id != library_id:
            raise LocalImportOwnerRequired
        expires_at = job.expires_at.replace(tzinfo=job.expires_at.tzinfo or UTC)
        if job.state != "READY" or expires_at <= datetime.now(UTC):
            raise LocalImportStateConflict("This import is no longer ready.")
        if job.reading_owner_user_id is None or self.repository.owner_membership(library_id, job.reading_owner_user_id) is None:
            raise LocalImportReadingOwnerInvalid
        repeated = any(item.get("code") == "REPEATED_ARCHIVE" for item in job.warnings)
        if repeated and not allow_repeated_archive:
            raise LocalImportStateConflict("Confirm that this repeated archive should create additional physical copies.")
        if self.object_storage is None or self.settings is None or self.storage_service is None:
            raise RuntimeError("Local import consolidation dependencies are unavailable.")
        extracted = self.staging_root / job.staging_key / "extracted"
        if not extracted.is_dir() or self._staging_fingerprint(extracted) != job.staging_sha256:
            raise LocalImportStateConflict("The validated import staging data changed or expired.")
        records = adapt_local_v8(extracted)
        if records.source_fingerprint != job.source_fingerprint:
            raise LocalImportStateConflict("The canonical import data changed after preflight.")

        stored_keys: list[str] = []
        try:
            job.state = "IMPORTING"
            self.repository.flush()
            counts, stored_keys = consolidate_local_v8(
                session=self.repository.session,
                storage=self.object_storage,
                settings=self.settings,
                records=records,
                extracted=extracted,
                library_id=library_id,
                reading_owner_user_id=job.reading_owner_user_id,
                actor_user_id=actor_user_id,
            )
            job.result_counts = counts
            job.state = "IMPORTED"
            job.completed_at = datetime.now(UTC)
            self.storage_service.prepare_owned_library_usage()
            self.repository.commit()
        except Exception:
            self.repository.rollback()
            for key in stored_keys:
                try:
                    self.object_storage.delete(key)
                except OSError:
                    pass
            raise
        shutil.rmtree(self.staging_root / job.staging_key, ignore_errors=True)
        return job
