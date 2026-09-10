from uuid import UUID

from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import Book, Bookcase, Library, LibraryImportJob, LibraryMembership, VisualOutsideArea


class LocalImportRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def owner_membership(self, library_id: UUID, user_id: UUID) -> LibraryMembership | None:
        return self.session.scalar(
            select(LibraryMembership).join(Library).where(
                LibraryMembership.library_id == library_id,
                LibraryMembership.user_id == user_id,
                LibraryMembership.role == "OWNER",
                Library.state == "active",
            )
        )

    def owner_user_ids(self, library_id: UUID) -> set[UUID]:
        return set(self.session.scalars(
            select(LibraryMembership.user_id).join(Library).where(
                LibraryMembership.library_id == library_id,
                LibraryMembership.role == "OWNER",
                Library.state == "active",
            )
        ))

    def destination_books(self, library_id: UUID) -> list[Book]:
        return list(
            self.session.scalars(
                select(Book).where(Book.library_id == library_id).order_by(Book.id)
            )
        )

    def destination_bookcase_names(self, library_id: UUID) -> set[str]:
        return {
            name.casefold()
            for name in self.session.scalars(
                select(Bookcase.name).where(Bookcase.library_id == library_id)
            )
        }

    def destination_outside_area_kinds(self, library_id: UUID) -> set[str]:
        return set(self.session.scalars(
            select(VisualOutsideArea.area_kind).where(
                VisualOutsideArea.library_id == library_id
            )
        ))

    def slug_exists(self, slug: str) -> bool:
        return bool(
            self.session.scalar(
                select(func.count()).select_from(Library).where(Library.slug == slug)
            )
        )

    def add_library(self, library: Library, membership: LibraryMembership) -> None:
        self.session.add_all((library, membership))

    def prior_jobs(self, library_id: UUID, archive_sha256: str) -> list[LibraryImportJob]:
        return list(
            self.session.scalars(
                select(LibraryImportJob).where(
                    LibraryImportJob.library_id == library_id,
                    LibraryImportJob.archive_sha256 == archive_sha256,
                    LibraryImportJob.state.in_(("READY", "IMPORTING", "IMPORTED")),
                )
            )
        )

    def add(self, job: LibraryImportJob) -> None:
        self.session.add(job)

    def find(self, import_id: UUID) -> LibraryImportJob | None:
        return self.session.get(LibraryImportJob, import_id)

    def lock(self, import_id: UUID) -> LibraryImportJob | None:
        return self.session.scalar(
            select(LibraryImportJob)
            .where(LibraryImportJob.id == import_id)
            .with_for_update()
        )

    def expired_staged_jobs(self, now: datetime) -> list[LibraryImportJob]:
        return list(
            self.session.scalars(
                select(LibraryImportJob).where(
                    LibraryImportJob.state.in_(("READY", "IMPORTING", "FAILED")),
                    LibraryImportJob.expires_at <= now,
                )
            )
        )

    def flush(self) -> None:
        self.session.flush()

    def commit(self) -> None:
        self.session.commit()

    def rollback(self) -> None:
        self.session.rollback()
