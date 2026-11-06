from collections.abc import Callable
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.api.dependencies import (
    get_local_import_service,
    get_portable_export_service,
)
from bookpile_server.config import get_settings
from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.models import (
    Book,
    BookContributor,
    BookCover,
    Bookcase,
    Container,
    Library,
    LibraryAuditEvent,
    LibraryImportJob,
    LibraryMembership,
    Loan,
    ReadingSession,
    Shelf,
    VisualBookcaseLayout,
    VisualContainerLayout,
    VisualOutsideArea,
    VisualShelfLayout,
)
from bookpile_server.repositories.imports import LocalImportRepository
from bookpile_server.services.local_imports import LocalImportService
from bookpile_server.services.portable_exports import PortableExportService
from test_local_zip_import import (
    CSRF,
    authenticated_user,
    create_backup,
    local_v8_database,
)


def _snapshot(
    session: Session,
    staging: Path,
    export_root: Path,
    object_root: Path,
) -> tuple[dict[str, tuple[tuple[Any, ...], ...]], tuple[tuple[str, bytes], ...]]:
    session.expire_all()

    def rows(model: type[Any]) -> tuple[tuple[Any, ...], ...]:
        values = session.execute(select(*model.__table__.columns)).all()
        return tuple(sorted((tuple(value) for value in values), key=repr))

    files = tuple(
        sorted(
            (
                (str(path.relative_to(root)), path.read_bytes())
                for root in (staging, export_root, object_root)
                if root.exists()
                for path in root.rglob("*")
                if path.is_file()
            ),
            key=repr,
        )
    )
    return (
        {
            "libraries": rows(Library),
            "memberships": rows(LibraryMembership),
            "jobs": rows(LibraryImportJob),
            "books": rows(Book),
            "book_contributors": rows(BookContributor),
            "book_covers": rows(BookCover),
            "bookcases": rows(Bookcase),
            "shelves": rows(Shelf),
            "containers": rows(Container),
            "readings": rows(ReadingSession),
            "loans": rows(Loan),
            "bookcase_layouts": rows(VisualBookcaseLayout),
            "shelf_layouts": rows(VisualShelfLayout),
            "container_layouts": rows(VisualContainerLayout),
            "outside_areas": rows(VisualOutsideArea),
            "audit": rows(LibraryAuditEvent),
        },
        files,
    )


def test_import_job_and_export_authorization_survive_stale_and_foreign_ids(
    client: TestClient,
    session: Session,
    tmp_path: Path,
) -> None:
    owner = authenticated_user(client, session, "a6_import_owner")
    settings = get_settings()
    owner_session_cookie = client.cookies.get(settings.session_cookie_name)
    owner_csrf_cookie = client.cookies.get(settings.csrf_cookie_name)
    assert owner_session_cookie is not None
    assert owner_csrf_cookie is not None

    viewer = authenticated_user(client, session, "a6_import_viewer")
    viewer_session_cookie = client.cookies.get(settings.session_cookie_name)
    viewer_csrf_cookie = client.cookies.get(settings.csrf_cookie_name)
    assert viewer_session_cookie is not None
    assert viewer_csrf_cookie is not None

    foreign_owner = authenticated_user(client, session, "a6_foreign_owner")
    foreign_session_cookie = client.cookies.get(settings.session_cookie_name)
    foreign_csrf_cookie = client.cookies.get(settings.csrf_cookie_name)
    assert foreign_session_cookie is not None
    assert foreign_csrf_cookie is not None

    library = Library(
        name="A6 import destination",
        slug="a6-import-destination",
        created_by_user_id=owner.id,
    )
    foreign_library = Library(
        name="A6 foreign library",
        slug="a6-foreign-library",
        created_by_user_id=foreign_owner.id,
    )
    session.add_all((library, foreign_library))
    session.flush()
    session.add_all(
        (
            LibraryMembership(
                library_id=library.id,
                user_id=owner.id,
                role="OWNER",
                selected_reading_user_id=owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=viewer.id,
                role="VIEWER",
                viewer_scope="CATALOG_AND_MAP",
                selected_reading_user_id=owner.id,
            ),
            LibraryMembership(
                library_id=foreign_library.id,
                user_id=foreign_owner.id,
                role="OWNER",
                selected_reading_user_id=foreign_owner.id,
            ),
        )
    )
    session.commit()

    staging = tmp_path / "a6-staging"
    export_root = tmp_path / "a6-exports"
    object_root = tmp_path / "a6-objects"
    import_service = LocalImportService(LocalImportRepository(session), staging)
    client.app.dependency_overrides[get_local_import_service] = lambda: import_service
    client.app.dependency_overrides[get_portable_export_service] = lambda: (
        PortableExportService(
            LocalImportRepository(session),
            FilesystemCoverStorage(object_root),
            export_root,
        )
    )

    database = tmp_path / "a6-source.db"
    archive = tmp_path / "a6-local.zip"
    local_v8_database(database)
    create_backup(archive, database)

    client.cookies.clear()
    client.cookies.set(settings.session_cookie_name, owner_session_cookie)
    client.cookies.set(settings.csrf_cookie_name, owner_csrf_cookie)
    with archive.open("rb") as upload:
        preflight = client.post(
            f"/api/v1/libraries/{library.id}/imports/local/preflight",
            data={"reading_owner_user_id": str(owner.id)},
            files={"backup": ("BOOKPILE.zip", upload, "application/zip")},
            headers={"X-CSRF-Token": CSRF},
        )
    assert preflight.status_code == 201, preflight.text
    import_id = preflight.json()["import_id"]
    assert client.get(
        f"/api/v1/libraries/{library.id}/imports/{import_id}"
    ).status_code == 200
    exported = client.get(
        f"/api/v1/libraries/{library.id}/exports/portable"
    )
    assert exported.status_code == 200
    assert exported.content.startswith(b"PK")
    assert list(export_root.glob("*.zip")) == []

    def restore_cookies(session_cookie: str, csrf_cookie: str) -> None:
        client.cookies.clear()
        client.cookies.set(settings.session_cookie_name, session_cookie)
        client.cookies.set(settings.csrf_cookie_name, csrf_cookie)

    def denied_job_operations(target_library_id: UUID) -> None:
        baseline = _snapshot(session, staging, export_root, object_root)
        operations: tuple[tuple[str, Callable[[], Any]], ...] = (
            (
                "read job",
                lambda: client.get(
                    f"/api/v1/libraries/{target_library_id}/imports/{import_id}"
                ),
            ),
            (
                "cancel job",
                lambda: client.delete(
                    f"/api/v1/libraries/{target_library_id}/imports/{import_id}",
                    headers={"X-CSRF-Token": CSRF},
                ),
            ),
            (
                "consolidate job",
                lambda: client.post(
                    f"/api/v1/libraries/{target_library_id}/imports/{import_id}/consolidate",
                    json={},
                    headers={"X-CSRF-Token": CSRF},
                ),
            ),
            (
                "consolidate as new library",
                lambda: client.post(
                    f"/api/v1/libraries/{target_library_id}/imports/{import_id}"
                    "/consolidate-new-library",
                    json={"name": "Forbidden restored library"},
                    headers={"X-CSRF-Token": CSRF},
                ),
            ),
        )
        for label, operation in operations:
            response = operation()
            assert response.status_code == 404, (label, response.text)
            assert _snapshot(session, staging, export_root, object_root) == baseline, label

    restore_cookies(viewer_session_cookie, viewer_csrf_cookie)
    viewer_preflight_baseline = _snapshot(session, staging, export_root, object_root)
    with archive.open("rb") as upload:
        denied_preflight = client.post(
            f"/api/v1/libraries/{library.id}/imports/local/preflight",
            data={"reading_owner_user_id": str(owner.id)},
            files={"backup": ("BOOKPILE.zip", upload, "application/zip")},
            headers={"X-CSRF-Token": CSRF},
        )
    assert denied_preflight.status_code == 404
    assert _snapshot(session, staging, export_root, object_root) == viewer_preflight_baseline
    denied_job_operations(library.id)
    viewer_export_baseline = _snapshot(session, staging, export_root, object_root)
    assert client.get(
        f"/api/v1/libraries/{library.id}/exports/portable"
    ).status_code == 404
    assert _snapshot(session, staging, export_root, object_root) == viewer_export_baseline

    restore_cookies(foreign_session_cookie, foreign_csrf_cookie)
    denied_job_operations(foreign_library.id)

    owner_membership = session.scalar(
        select(LibraryMembership).where(
            LibraryMembership.library_id == library.id,
            LibraryMembership.user_id == owner.id,
        )
    )
    assert owner_membership is not None
    session.delete(owner_membership)
    session.commit()
    restore_cookies(owner_session_cookie, owner_csrf_cookie)
    denied_job_operations(library.id)
    stale_export_baseline = _snapshot(session, staging, export_root, object_root)
    assert client.get(
        f"/api/v1/libraries/{library.id}/exports/portable"
    ).status_code == 404
    assert _snapshot(session, staging, export_root, object_root) == stale_export_baseline
