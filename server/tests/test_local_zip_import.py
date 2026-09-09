from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
import sqlite3
import zipfile
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from PIL import Image
import pytest

from bookpile_server.imports.local_zip import (
    LocalArchiveLimits,
    LocalImportValidationError,
    inspect_local_backup,
    adapt_local_v8,
)
from bookpile_server.api.dependencies import get_local_import_service, get_portable_export_service
from bookpile_server.config import get_settings
from bookpile_server.models import (
    Book,
    AccountStorageEntitlement,
    BookContributor,
    Bookcase,
    ContributorRole,
    Library,
    LibraryImportJob,
    LibraryMembership,
    Loan,
    ReadingSession,
    User,
    UserSession,
    VisualBookcaseLayout,
    VisualShelfLayout,
)
from bookpile_server.cover_storage import FilesystemCoverStorage
from bookpile_server.repositories.imports import LocalImportRepository
from bookpile_server.services.auth import hash_session_secret
from bookpile_server.services.local_imports import LocalImportService
from bookpile_server.repositories.storage import StorageRepository
from bookpile_server.services.storage import StorageService
from bookpile_server.services.storage_domain import InsufficientSharedCapacity
from bookpile_server.exports.server_library import create_server_library_export
from bookpile_server.services.portable_exports import PortableExportService


CSRF = "local-import-csrf"


def webp_bytes() -> bytes:
    output = BytesIO()
    Image.new("RGB", (8, 12), "navy").save(output, "WEBP")
    return output.getvalue()


def local_v8_database(path: Path, *, cover_filename: str | None = "cover.webp") -> None:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.executescript(
        """
        CREATE TABLE bookcases (id INTEGER PRIMARY KEY, name TEXT, description TEXT);
        CREATE TABLE shelves (
            id INTEGER PRIMARY KEY,
            bookcase_id INTEGER REFERENCES bookcases(id),
            shelf_number INTEGER
        );
        CREATE TABLE containers (
            id INTEGER PRIMARY KEY,
            shelf_id INTEGER REFERENCES shelves(id),
            container_type TEXT,
            layer TEXT,
            container_number INTEGER
        );
        CREATE TABLE books (
            id INTEGER PRIMARY KEY,
            title TEXT,
            author TEXT,
            has_multiple_authors INTEGER DEFAULT 0,
            isbn_10 TEXT, isbn_13 TEXT, subtitle TEXT, page_count INTEGER,
            publisher TEXT, current_ed_year INTEGER,
            original_publication_year INTEGER, language TEXT,
            edition_number INTEGER, fiction_category TEXT, binding TEXT,
            publication_type TEXT, genre_text TEXT, series_name TEXT,
            series_volume TEXT, status TEXT DEFAULT 'PENDING',
            goodreads_url TEXT, notes TEXT, acquisition_date TEXT,
            reading_started_date TEXT, read_date TEXT,
            is_read_date_unknown INTEGER DEFAULT 0,
            is_original_collection INTEGER DEFAULT 0,
            cover_filename TEXT,
            container_id INTEGER REFERENCES containers(id),
            position INTEGER, created_at TEXT, updated_at TEXT
        );
        CREATE TABLE book_authors (
            book_id INTEGER REFERENCES books(id), position INTEGER, name TEXT
        );
        CREATE TABLE reading_sessions (
            id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id),
            session_number INTEGER, state TEXT, started_date TEXT,
            finished_date TEXT, dates_unknown INTEGER,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE loans (
            id INTEGER PRIMARY KEY, book_id INTEGER REFERENCES books(id),
            loaned_to TEXT, notes TEXT, state TEXT, loaned_date TEXT,
            expected_return_date TEXT, returned_date TEXT,
            created_at TEXT, updated_at TEXT
        );
        CREATE TABLE visual_layout_items (
            item_type TEXT, item_id INTEGER, x REAL, y REAL, width REAL, height REAL
        );
        CREATE TABLE visual_shelf_layout (
            shelf_id INTEGER REFERENCES shelves(id), height_weight REAL
        );
        CREATE TABLE visual_container_layout (
            container_id INTEGER REFERENCES containers(id),
            x REAL, y REAL, width REAL, height REAL,
            row_anchor TEXT, pile_support_kind TEXT,
            pile_support_container_id INTEGER REFERENCES containers(id)
        );
        CREATE TABLE schema_migrations (version INTEGER PRIMARY KEY, name TEXT);
        INSERT INTO schema_migrations(version, name) VALUES
            (1, 'baseline'), (2, 'isbn'), (3, 'metadata'), (4, 'authors'),
            (5, 'readings'), (6, 'loans'), (7, 'world'), (8, 'visual semantics');
        INSERT INTO bookcases VALUES (1, 'Office', 'Test furniture');
        INSERT INTO shelves VALUES (2, 1, 1);
        INSERT INTO containers VALUES (3, 2, 'ROW', 'BACKGROUND', 1);
        INSERT INTO books (
            id, title, author, has_multiple_authors, status, is_read_date_unknown,
            cover_filename, container_id, position,
            created_at, updated_at
        ) VALUES (4, 'A book', 'Multiple authors', 1, 'READ', 1, NULL, 3, 1,
                  '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        INSERT INTO book_authors VALUES (4, 1, 'First author');
        INSERT INTO book_authors VALUES (4, 2, 'Second author');
        INSERT INTO reading_sessions VALUES
            (5, 4, 1, 'COMPLETED', NULL, NULL, 1,
             '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        INSERT INTO loans VALUES
            (6, 4, 'A friend', NULL, 'RETURNED', NULL, NULL, NULL,
             '2026-01-01 00:00:00', '2026-01-01 00:00:00');
        INSERT INTO visual_layout_items VALUES ('BOOKCASE', 1, 0, 0, 100, 100);
        INSERT INTO visual_shelf_layout VALUES (2, 1);
        INSERT INTO visual_container_layout
            VALUES (3, 0, 0, 100, 100, 'LEFT', NULL, NULL);
        """
    )
    connection.execute(
        "UPDATE books SET cover_filename = ? WHERE id = 4", (cover_filename,)
    )
    connection.commit()
    connection.close()


def create_backup(
    path: Path,
    database: Path,
    *,
    schema_version: int = 8,
    extra_entries: dict[str, bytes] | None = None,
    bad_database_checksum: bool = False,
) -> None:
    covers = {"covers/cover.webp": webp_bytes()}
    files = {"bookpile.db": database.read_bytes(), **covers}
    manifest_files = {
        name: {"size": len(content), "sha256": sha256(content).hexdigest()}
        for name, content in files.items()
    }
    if bad_database_checksum:
        manifest_files["bookpile.db"]["sha256"] = "0" * 64
    manifest = {
        "format": "BOOKPILE_BACKUP",
        "backup_format_version": 1,
        "schema_version": schema_version,
        "created_at": "2026-09-09T12:00:00+00:00",
        "integrity_check": "ok",
        "counts": {
            "bookcases": 1,
            "shelves": 1,
            "containers": 1,
            "books": 1,
            "book_authors": 2,
            "reading_sessions": 1,
            "loans": 1,
            "covers": 1,
        },
        "files": manifest_files,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest))
        for name, content in files.items():
            archive.writestr(name, content)
        for name, content in (extra_entries or {}).items():
            archive.writestr(name, content)


def test_inspects_valid_local_v8_backup_without_server_writes(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    archive = tmp_path / "local.zip"
    local_v8_database(database)
    create_backup(archive, database)

    result = inspect_local_backup(archive, tmp_path / "isolated")

    assert result.adapter == "local-v8"
    assert result.local_schema_version == 8
    assert result.counts["books"] == 1
    assert result.counts["covers"] == 1
    assert result.estimated_cover_bytes > 0
    assert len(result.archive_sha256) == 64
    assert (tmp_path / "isolated" / "bookpile.db").is_file()

    canonical = adapt_local_v8(tmp_path / "isolated")
    assert canonical.books[0]["title"] == "A book"
    assert canonical.contributors[0] == {
        "source_book_id": 4,
        "role_code": "AUTHOR",
        "position": 1,
        "name": "First author",
    }
    assert canonical.readings[0]["source_book_id"] == 4
    assert canonical.loans[0]["loaned_to"] == "A friend"
    assert canonical.outside_areas == ()
    assert len(canonical.source_fingerprint) == 64


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("checksum", "Checksum mismatch"),
        ("schema", "No safe importer"),
        ("extra", "Unsafe ZIP entry"),
    ],
)
def test_rejects_untrusted_archive_before_import(
    tmp_path: Path, change: str, message: str
) -> None:
    database = tmp_path / "source.db"
    archive = tmp_path / "local.zip"
    local_v8_database(database)
    create_backup(
        archive,
        database,
        schema_version=9 if change == "schema" else 8,
        bad_database_checksum=change == "checksum",
        extra_entries={"../escape.txt": b"bad"} if change == "extra" else None,
    )

    with pytest.raises(LocalImportValidationError, match=message):
        inspect_local_backup(archive, tmp_path / "isolated")
    assert not (tmp_path / "isolated").exists()


def test_rejects_archive_over_compressed_size_limit(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    archive = tmp_path / "local.zip"
    local_v8_database(database)
    create_backup(archive, database)

    with pytest.raises(LocalImportValidationError, match="100 MiB or smaller"):
        inspect_local_backup(
            archive,
            tmp_path / "isolated",
            limits=LocalArchiveLimits(max_archive_bytes=archive.stat().st_size - 1),
        )


def test_rejects_missing_referenced_cover(tmp_path: Path) -> None:
    database = tmp_path / "source.db"
    archive = tmp_path / "local.zip"
    local_v8_database(database, cover_filename="different.webp")
    create_backup(archive, database)

    with pytest.raises(LocalImportValidationError, match="Archived covers"):
        inspect_local_backup(archive, tmp_path / "isolated")
    assert not (tmp_path / "isolated").exists()


def authenticated_user(client, session, username: str) -> User:
    user = User(
        email=f"{username}@example.test",
        username=username,
        password_hash="unused",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    session.add(user)
    session.flush()
    raw_token = f"import-{uuid4().hex}"
    now = datetime.now(UTC)
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_secret(raw_token),
            csrf_token_hash=hash_session_secret(CSRF),
            last_seen_at=now,
            expires_at=now + timedelta(days=7),
            absolute_expires_at=now + timedelta(days=30),
        )
    )
    session.commit()
    settings = get_settings()
    client.cookies.set(settings.session_cookie_name, raw_token)
    client.cookies.set(settings.csrf_cookie_name, CSRF)
    return user


def test_owner_preflight_persists_report_but_not_uploaded_zip(
    client, session, tmp_path: Path
) -> None:
    owner = authenticated_user(client, session, "import_owner")
    reading_owner = User(
        email="reader@example.test",
        username="import_reader",
        password_hash="unused",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    library = Library(name="Imported home", slug="imported-home", created_by_user_id=owner.id)
    session.add_all([reading_owner, library])
    session.flush()
    session.add_all(
        [
            LibraryMembership(
                library_id=library.id,
                user_id=owner.id,
                role="OWNER",
                selected_reading_user_id=owner.id,
            ),
            LibraryMembership(
                library_id=library.id,
                user_id=reading_owner.id,
                role="OWNER",
                selected_reading_user_id=reading_owner.id,
            ),
        ]
    )
    session.commit()
    staging = tmp_path / "staging"
    client.app.dependency_overrides[get_local_import_service] = lambda: LocalImportService(
        LocalImportRepository(session), staging
    )
    database = tmp_path / "source.db"
    archive = tmp_path / "local.zip"
    local_v8_database(database)
    create_backup(archive, database)

    with archive.open("rb") as source:
        response = client.post(
            f"/api/v1/libraries/{library.id}/imports/local/preflight",
            data={"reading_owner_user_id": str(reading_owner.id)},
            files={"backup": ("BOOKPILE.zip", source, "application/zip")},
            headers={"X-CSRF-Token": CSRF},
        )

    assert response.status_code == 201, response.text
    report = response.json()
    assert report["state"] == "READY"
    assert report["library_id"] == str(library.id)
    assert report["adapter"] == "local-v8"
    assert report["reading_owner_user_id"] == str(reading_owner.id)
    assert report["counts"]["books"] == 1
    job = session.get(LibraryImportJob, UUID(report["import_id"]))
    assert job is not None and job.state == "READY"
    directory = staging / str(job.id)
    assert not (directory / "upload.zip").exists()
    assert (directory / "extracted" / "bookpile.db").is_file()

    with archive.open("rb") as source:
        repeated = client.post(
            f"/api/v1/libraries/{library.id}/imports/local/preflight",
            data={"reading_owner_user_id": str(reading_owner.id)},
            files={"backup": ("BOOKPILE.zip", source, "application/zip")},
            headers={"X-CSRF-Token": CSRF},
        )
    assert repeated.status_code == 201
    assert "REPEATED_ARCHIVE" in {item["code"] for item in repeated.json()["warnings"]}

    fetched = client.get(f"/api/v1/libraries/{library.id}/imports/{job.id}")
    assert fetched.status_code == 200
    assert fetched.json()["capacity_available"] is True
    cancelled = client.delete(
        f"/api/v1/libraries/{library.id}/imports/{job.id}",
        headers={"X-CSRF-Token": CSRF},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["state"] == "EXPIRED"
    assert not directory.exists()


def test_atomic_consolidation_preserves_catalogue_readings_loans_and_layout(
    session, tmp_path: Path
) -> None:
    owner = User(
        email="atomic@example.test",
        username="atomic_owner",
        password_hash="unused",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    library = Library(name="Atomic destination", slug="atomic-destination", created_by_user_id=owner.id)
    session.add_all([owner, library, ContributorRole(code="AUTHOR", label="Author", sort_order=1)])
    session.flush()
    session.add(AccountStorageEntitlement(user_id=owner.id))
    session.add(
        LibraryMembership(
            library_id=library.id,
            user_id=owner.id,
            role="OWNER",
            selected_reading_user_id=owner.id,
        )
    )
    session.commit()
    staging = tmp_path / "atomic-staging"
    objects = FilesystemCoverStorage(tmp_path / "objects")
    service = LocalImportService(
        LocalImportRepository(session),
        staging,
        storage_service=StorageService(StorageRepository(session)),
        object_storage=objects,
        settings=get_settings(),
    )
    database = tmp_path / "atomic-source.db"
    archive = tmp_path / "atomic-local.zip"
    local_v8_database(database)
    connection = sqlite3.connect(database)
    connection.execute(
        "UPDATE books SET goodreads_url = 'https://www.goodreads.com/review/show/123'"
    )
    connection.commit()
    connection.close()
    create_backup(archive, database)
    with archive.open("rb") as source:
        job = service.preflight(
            library_id=library.id,
            actor_user_id=owner.id,
            reading_owner_user_id=owner.id,
            upload=source,
        )

    completed = service.consolidate(
        import_id=job.id,
        library_id=library.id,
        actor_user_id=owner.id,
        allow_repeated_archive=False,
    )

    assert completed.state == "IMPORTED"
    assert completed.result_counts == {
        "bookcases": 1,
        "shelves": 1,
        "containers": 1,
        "books": 1,
        "contributors": 2,
        "readings": 1,
        "loans": 1,
        "covers": 1,
    }
    imported_book = session.query(Book).filter_by(library_id=library.id).one()
    assert imported_book.title == "A book"
    assert [item.name for item in session.query(BookContributor).filter_by(book_id=imported_book.id).order_by(BookContributor.position)] == ["First author", "Second author"]
    assert session.query(ReadingSession).filter_by(book_id=imported_book.id).one().user_id == owner.id
    assert session.query(Loan).filter_by(book_id=imported_book.id).one().loaned_to == "A friend"
    imported_case = session.query(Bookcase).filter_by(library_id=library.id).one()
    case_layout = session.get(VisualBookcaseLayout, (library.id, imported_case.id))
    assert case_layout is not None and float(case_layout.width_mm) == 2500
    shelf_layout = session.query(VisualShelfLayout).filter_by(library_id=library.id).one()
    assert float(shelf_layout.width_mm) == 2375
    assert not (staging / str(job.id)).exists()
    cover = imported_book.cover
    assert cover is not None and objects.read(cover.object_key)

    export_path = tmp_path / "portable.zip"
    manifest = create_server_library_export(
        session=session,
        storage=objects,
        library_id=library.id,
        destination=export_path,
    )
    assert manifest["format"] == "BOOKPILE_SERVER_LIBRARY"
    with zipfile.ZipFile(export_path) as portable:
        assert set(portable.namelist()) == {
            "manifest.json",
            "library.json",
            f"covers/{imported_book.id}.webp",
        }
        data_bytes = portable.read("library.json")
        exported = json.loads(data_bytes)
    assert exported["library"]["name"] == "Atomic destination"
    assert exported["members"] == [
        {
            "member_key": str(owner.id),
            "role": "OWNER",
            "selected_reading_member_key": str(owner.id),
            "username": "atomic_owner",
            "viewer_scope": None,
        }
    ]
    assert exported["readings"][0]["user_id"] == str(owner.id)
    assert "atomic@example.test" not in data_bytes.decode("utf-8")
    assert "password" not in data_bytes.decode("utf-8").casefold()


def test_new_library_and_local_data_are_created_in_one_transaction(
    session, tmp_path: Path
) -> None:
    owner = User(
        email="new-import@example.test", username="new_import_owner",
        password_hash="unused", state="active", email_verified_at=datetime.now(UTC),
    )
    source = Library(name="Inspection source", slug="inspection-source", created_by_user_id=owner.id)
    session.add_all([owner, source, ContributorRole(code="AUTHOR", label="Author", sort_order=1)])
    session.flush()
    session.add_all([
        AccountStorageEntitlement(user_id=owner.id),
        LibraryMembership(library_id=source.id, user_id=owner.id, role="OWNER", selected_reading_user_id=owner.id),
    ])
    session.commit()
    service = LocalImportService(
        LocalImportRepository(session), tmp_path / "new-library-staging",
        storage_service=StorageService(StorageRepository(session)),
        object_storage=FilesystemCoverStorage(tmp_path / "new-library-objects"),
        settings=get_settings(),
    )
    database = tmp_path / "new-library.db"
    archive = tmp_path / "new-library.zip"
    local_v8_database(database)
    create_backup(archive, database)
    with archive.open("rb") as upload:
        job = service.preflight(
            library_id=source.id, actor_user_id=owner.id,
            reading_owner_user_id=owner.id, upload=upload,
        )

    completed = service.consolidate_as_new_library(
        import_id=job.id, source_library_id=source.id, actor_user_id=owner.id,
        name="Imported separately", allow_repeated_archive=False,
    )

    created = session.get(Library, completed.library_id)
    assert created is not None and created.name == "Imported separately"
    assert session.query(Book).filter_by(library_id=created.id).count() == 1
    membership = session.query(LibraryMembership).filter_by(library_id=created.id).one()
    assert membership.user_id == owner.id and membership.role == "OWNER"
    assert session.query(ReadingSession).join(Book).filter(Book.library_id == created.id).one().user_id == owner.id

def test_failed_final_quota_check_rolls_back_rows_and_cover_objects(
    session, tmp_path: Path
) -> None:
    owner = User(
        email="rollback@example.test",
        username="rollback_owner",
        password_hash="unused",
        state="active",
        email_verified_at=datetime.now(UTC),
    )
    library = Library(name="Rollback", slug="rollback-import", created_by_user_id=owner.id)
    session.add_all([owner, library, ContributorRole(code="AUTHOR", label="Author", sort_order=1)])
    session.flush()
    session.add_all(
        [
            AccountStorageEntitlement(user_id=owner.id, limit_bytes=100),
            LibraryMembership(
                library_id=library.id,
                user_id=owner.id,
                role="OWNER",
                selected_reading_user_id=owner.id,
            ),
        ]
    )
    session.commit()
    staging = tmp_path / "rollback-staging"
    object_root = tmp_path / "rollback-objects"
    objects = FilesystemCoverStorage(object_root)
    service = LocalImportService(
        LocalImportRepository(session),
        staging,
        storage_service=StorageService(StorageRepository(session)),
        object_storage=objects,
        settings=get_settings(),
    )
    database = tmp_path / "rollback.db"
    archive = tmp_path / "rollback.zip"
    local_v8_database(database)
    create_backup(archive, database)
    with archive.open("rb") as source:
        job = service.preflight(
            library_id=library.id,
            actor_user_id=owner.id,
            reading_owner_user_id=owner.id,
            upload=source,
        )
    assert job.capacity_available is False

    with pytest.raises(InsufficientSharedCapacity):
        service.consolidate(
            import_id=job.id,
            library_id=library.id,
            actor_user_id=owner.id,
            allow_repeated_archive=False,
        )

    session.expire_all()
    assert session.query(Book).filter_by(library_id=library.id).count() == 0
    assert session.query(Bookcase).filter_by(library_id=library.id).count() == 0
    assert session.get(LibraryImportJob, job.id).state == "READY"
    assert list(object_root.rglob("*.webp")) == []
    assert (staging / str(job.id) / "extracted" / "bookpile.db").is_file()

    with pytest.raises(InsufficientSharedCapacity):
        service.consolidate_as_new_library(
            import_id=job.id,
            source_library_id=library.id,
            actor_user_id=owner.id,
            name="Must roll back",
            allow_repeated_archive=False,
        )
    session.expire_all()
    assert session.query(Library).filter_by(name="Must roll back").count() == 0
    assert session.get(LibraryImportJob, job.id).library_id == library.id


def test_portable_export_endpoint_is_owner_only_and_removes_temporary_zip(
    client, session, tmp_path: Path
) -> None:
    owner = authenticated_user(client, session, "export_owner")
    library = Library(name="Owner export", slug="owner-export", created_by_user_id=owner.id)
    session.add(library)
    session.flush()
    session.add(
        LibraryMembership(
            library_id=library.id,
            user_id=owner.id,
            role="OWNER",
            selected_reading_user_id=owner.id,
        )
    )
    session.commit()
    export_root = tmp_path / "exports"
    client.app.dependency_overrides[get_portable_export_service] = lambda: PortableExportService(
        LocalImportRepository(session),
        FilesystemCoverStorage(tmp_path / "export-objects"),
        export_root,
    )

    response = client.get(f"/api/v1/libraries/{library.id}/exports/portable")

    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert response.headers["content-type"] == "application/zip"
    assert list(export_root.glob("*.zip")) == []

    viewer = authenticated_user(client, session, "export_viewer")
    session.add(
        LibraryMembership(
            library_id=library.id,
            user_id=viewer.id,
            role="VIEWER",
            viewer_scope="CATALOG_AND_MAP",
            selected_reading_user_id=owner.id,
        )
    )
    session.commit()
    assert client.get(f"/api/v1/libraries/{library.id}/exports/portable").status_code == 404
