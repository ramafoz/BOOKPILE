import os
import json
import sqlite3
import statistics as statistics_module
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Any, Literal
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from starlette.background import BackgroundTask
from PIL import Image, ImageOps, UnidentifiedImageError
from pillow_heif import register_heif_opener

from .bibliography import BibliographicProvidersUnavailable, lookup_isbn
from .catalogue_matching import (
    add_catalogue_matches,
    find_catalogue_matches,
    find_isbn_catalogue_matches,
)
from .database import connect, database_path, init_database
from .exports import create_full_backup, write_books_csv, write_reading_sessions_csv
from .isbn import InvalidISBN, normalize_isbn
from .rearrangement import (
    apply_planned_books,
    load_rearrangement_state,
    plan_rearrangement_draft,
    rearrangement_revision,
)
from .reading_sessions import (
    ReadingSessionError,
    add_historical_reading,
    apply_projected_reading_values,
    cancel_active_reading,
    delete_all_sessions,
    delete_session,
    finish_reading,
    start_reading,
    sync_book_projection,
    update_session,
)
from .restore import MAX_BACKUP_BYTES, perform_restore, stage_restore
from .schemas import (
    Binding,
    Book,
    BookCreate,
    BookMove,
    BookStatus,
    BookUpdate,
    BookcaseCreate,
    BookcaseUpdate,
    CatalogueMatch,
    CatalogueMatchRequest,
    ContainerCreate,
    ContainerUpdate,
    FictionCategory,
    ISBNLookupResult,
    PublicationType,
    ReadingFinishRequest,
    ReadingHistoryCreate,
    ReadingHistoryUpdate,
    ReadingStartRequest,
    RearrangementApplyRequest,
    RearrangementRequest,
    RearrangementResult,
    ShelfCreate,
    ShelfUpdate,
    Stats,
    VisualLayoutUpdate,
)


BOOK_SELECT = """
SELECT
    b.*,
    COALESCE((
        SELECT json_group_array(ordered.name)
        FROM (
            SELECT name FROM book_authors
            WHERE book_id = b.id ORDER BY position
        ) ordered
    ), '[]') AS structured_authors_json,
    COALESCE((
        SELECT json_group_array(json(ordered_session.session_json))
        FROM (
            SELECT json_object(
                'id', rs.id,
                'book_id', rs.book_id,
                'session_number', rs.session_number,
                'state', rs.state,
                'started_date', rs.started_date,
                'finished_date', rs.finished_date,
                'dates_unknown', json(CASE WHEN rs.dates_unknown = 1 THEN 'true' ELSE 'false' END),
                'created_at', rs.created_at,
                'updated_at', rs.updated_at
            ) AS session_json
            FROM reading_sessions rs
            WHERE rs.book_id = b.id
            ORDER BY rs.session_number
        ) ordered_session
    ), '[]') AS reading_sessions_json,
    bc.name AS bookcase_name,
    s.shelf_number,
    c.container_type,
    c.layer,
    c.container_number
FROM books b
LEFT JOIN containers c ON c.id = b.container_id
LEFT JOIN shelves s ON s.id = c.shelf_id
LEFT JOIN bookcases bc ON bc.id = s.bookcase_id
"""

MAX_COVER_BYTES = 12 * 1024 * 1024
MAX_COVER_SIZE = (900, 1400)
ALLOWED_COVER_FORMATS = {"JPEG", "PNG", "WEBP", "HEIF"}
register_heif_opener()


def covers_directory() -> Path:
    directory = database_path().parent / "covers"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def delete_cover_file(filename: str | None) -> None:
    if filename:
        (covers_directory() / filename).unlink(missing_ok=True)


def temporary_download(suffix: str) -> Path:
    descriptor, filename = tempfile.mkstemp(
        prefix="bookpile-download-",
        suffix=suffix,
    )
    os.close(descriptor)
    Path(filename).unlink(missing_ok=True)
    return Path(filename)


def serialize_book(row: sqlite3.Row) -> dict[str, Any]:
    book = dict(row)
    book["structured_authors"] = json.loads(
        book.pop("structured_authors_json", "[]")
    )
    book["reading_sessions"] = json.loads(
        book.pop("reading_sessions_json", "[]")
    )
    book["reading_session_count"] = len(book["reading_sessions"])
    book["is_rereading"] = any(
        session["state"] == "ACTIVE" for session in book["reading_sessions"]
    ) and any(
        session["state"] == "COMPLETED" for session in book["reading_sessions"]
    )
    if book["container_id"] is None:
        book["location_label"] = None
    else:
        layer = book["layer"].title()
        kind = book["container_type"].title()
        book["location_label"] = (
            f'{book["bookcase_name"]} · Shelf {book["shelf_number"]} · '
            f'{layer} {kind} {book["container_number"]} · Position {book["position"]}'
        )
    return book


def fetch_book(book_id: int) -> dict[str, Any]:
    with connect() as connection:
        row = connection.execute(
            f"{BOOK_SELECT} WHERE b.id = ?", (book_id,)
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Book not found")
    return serialize_book(row)


def metadata_filter_conditions(
    where: list[str],
    params: list[Any],
    *,
    isbn: str | None = None,
    languages: list[str] | None = None,
    genres: list[str] | None = None,
    publishers: list[str] | None = None,
    fiction_categories: list[FictionCategory] | None = None,
    bindings: list[Binding] | None = None,
    publication_types: list[PublicationType] | None = None,
    series_names: list[str] | None = None,
    series_state: Literal["ANY", "YES", "NO"] = "ANY",
    author_structure: Literal["ANY", "SINGLE", "MULTIPLE"] = "ANY",
    page_min: int | None = None,
    page_max: int | None = None,
    publication_year_field: Literal[
        "current_ed_year", "original_publication_year"
    ] = "current_ed_year",
    publication_year_min: int | None = None,
    publication_year_max: int | None = None,
) -> None:
    if page_min is not None and page_max is not None and page_min > page_max:
        raise HTTPException(
            status_code=422,
            detail="Minimum pages must be less than or equal to maximum pages",
        )
    if (
        publication_year_min is not None
        and publication_year_max is not None
        and publication_year_min > publication_year_max
    ):
        raise HTTPException(
            status_code=422,
            detail="Minimum year must be less than or equal to maximum year",
        )

    if isbn and isbn.strip():
        try:
            normalized_isbn = normalize_isbn(isbn)
        except InvalidISBN as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        where.append("(b.isbn_10 = ? OR b.isbn_13 = ?)")
        params.extend((normalized_isbn, normalized_isbn))

    def add_exact_values(column: str, values: list[Any] | None) -> None:
        cleaned = [
            value.value if hasattr(value, "value") else str(value).strip()
            for value in (values or [])
            if str(value.value if hasattr(value, "value") else value).strip()
        ]
        if not cleaned:
            return
        placeholders = ", ".join("?" for _ in cleaned)
        where.append(f"{column} IN ({placeholders})")
        params.extend(cleaned)

    add_exact_values("b.language", languages)
    add_exact_values("b.publisher", publishers)
    add_exact_values("b.fiction_category", fiction_categories)
    add_exact_values("b.binding", bindings)
    add_exact_values("b.publication_type", publication_types)
    add_exact_values("b.series_name", series_names)

    cleaned_genres = [value.strip() for value in (genres or []) if value.strip()]
    if cleaned_genres:
        normalized_genres = (
            "',' || lower(replace(replace(replace("
            "b.genre_text, ' ', ''), char(9), ''), char(10), '')) || ','"
        )
        where.append(
            "(" + " OR ".join(
                f"instr({normalized_genres}, ?) > 0" for _ in cleaned_genres
            ) + ")"
        )
        params.extend(
            f",{''.join(value.split()).lower()}," for value in cleaned_genres
        )

    if series_state == "YES":
        where.append("(b.series_name IS NOT NULL AND trim(b.series_name) <> '')")
    elif series_state == "NO":
        where.append("(b.series_name IS NULL OR trim(b.series_name) = '')")
    if author_structure == "MULTIPLE":
        where.append("b.has_multiple_authors = 1")
    elif author_structure == "SINGLE":
        where.append("b.has_multiple_authors = 0")
    if page_min is not None:
        where.append("b.page_count >= ?")
        params.append(page_min)
    if page_max is not None:
        where.append("b.page_count <= ?")
        params.append(page_max)
    if publication_year_min is not None:
        where.append(f"b.{publication_year_field} >= ?")
        params.append(publication_year_min)
    if publication_year_max is not None:
        where.append(f"b.{publication_year_field} <= ?")
        params.append(publication_year_max)


def location_values(payload: BookCreate | BookUpdate) -> tuple[int | None, int | None]:
    fields_set = payload.model_fields_set
    if isinstance(payload, BookUpdate) and not ({"container_id", "position"} & fields_set):
        return (None, None)

    container_id = payload.container_id
    position = payload.position
    if (container_id is None) != (position is None):
        raise HTTPException(
            status_code=422,
            detail="Container and position must be supplied together",
        )
    return container_id, position


def ensure_container_exists(connection: sqlite3.Connection, container_id: int) -> None:
    container_exists = connection.execute(
        "SELECT 1 FROM containers WHERE id = ?", (container_id,)
    ).fetchone()
    if container_exists is None:
        raise HTTPException(status_code=404, detail="Container not found")


def make_room_for_position(
    connection: sqlite3.Connection,
    container_id: int,
    position: int,
) -> None:
    rows = connection.execute(
        """
        SELECT id, position
        FROM books
        WHERE container_id = ? AND position >= ?
        ORDER BY position DESC
        """,
        (container_id, position),
    ).fetchall()
    for row in rows:
        connection.execute(
            """
            UPDATE books
            SET position = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["position"] + 1, row["id"]),
        )


def close_position_gap(
    connection: sqlite3.Connection,
    container_id: int | None,
    position: int | None,
) -> None:
    if container_id is None or position is None:
        return

    rows = connection.execute(
        """
        SELECT id, position
        FROM books
        WHERE container_id = ? AND position > ?
        ORDER BY position ASC
        """,
        (container_id, position),
    ).fetchall()
    for row in rows:
        connection.execute(
            """
            UPDATE books
            SET position = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (row["position"] - 1, row["id"]),
        )


def validate_book_dates(
    acquisition_date: date | None,
    reading_started_date: date | None,
    read_date: date | None,
) -> None:
    if (
        acquisition_date is not None
        and reading_started_date is not None
        and reading_started_date < acquisition_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Reading started date cannot be earlier than acquisition date",
        )
    if (
        reading_started_date is not None
        and read_date is not None
        and read_date < reading_started_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Finished reading date cannot be earlier than reading started date",
        )
    if (
        acquisition_date is not None
        and read_date is not None
        and read_date < acquisition_date
    ):
        raise HTTPException(
            status_code=422,
            detail="Finished reading date cannot be earlier than acquisition date",
        )


def parsed_date(value: str | date | None) -> date | None:
    if value is None or isinstance(value, date):
        return value
    return date.fromisoformat(value)


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_database()
    yield


app = FastAPI(
    title="BOOKPILE API",
    description="Personal library catalogue and physical location map.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_origin_regex=(
        r"^https?://("
        r"localhost|127\.0\.0\.1|"
        r"10(?:\.\d{1,3}){3}|"
        r"192\.168(?:\.\d{1,3}){2}|"
        r"172\.(?:1[6-9]|2\d|3[01])(?:\.\d{1,3}){2}"
        r")(?::\d+)?$"
    ),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/bibliography/isbn", response_model=ISBNLookupResult)
def lookup_isbn_metadata(isbn: str = Query(min_length=1, max_length=40)) -> dict[str, Any]:
    try:
        normalized = normalize_isbn(isbn)
        catalogue_matches = find_isbn_catalogue_matches(normalized)
        candidates = add_catalogue_matches(lookup_isbn(normalized))
    except InvalidISBN as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except BibliographicProvidersUnavailable as exc:
        if catalogue_matches:
            return {
                "isbn": normalized,
                "candidates": [],
                "catalogue_matches": catalogue_matches,
            }
        raise HTTPException(
            status_code=503,
            detail="Bibliographic lookup services are temporarily unavailable",
        ) from exc
    return {
        "isbn": normalized,
        "candidates": candidates,
        "catalogue_matches": catalogue_matches,
    }


@app.post("/bibliography/matches", response_model=list[CatalogueMatch])
def match_bibliographic_text(payload: CatalogueMatchRequest) -> list[dict[str, Any]]:
    return find_catalogue_matches(payload.title, payload.authors)


@app.post("/rearrangements/preview", response_model=RearrangementResult)
def preview_rearrangement(payload: RearrangementRequest) -> dict[str, Any]:
    with connect() as connection:
        books, containers = load_rearrangement_state(connection)
    return plan_rearrangement_draft(books, containers, payload)


@app.post("/rearrangements/apply", response_model=RearrangementResult)
def apply_rearrangement(payload: RearrangementApplyRequest) -> dict[str, Any]:
    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            books, containers = load_rearrangement_state(connection)
            if rearrangement_revision(books) != payload.revision:
                raise HTTPException(
                    status_code=409,
                    detail="The catalogue changed after this rearrangement was previewed",
                )
            result = plan_rearrangement_draft(books, containers, payload)
            if not result["valid_to_apply"]:
                raise HTTPException(
                    status_code=409,
                    detail="Complete the chain and resolve every gap before applying",
                )
            apply_planned_books(connection, books, result["_planned_books"])
    except ReadingSessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return result


@app.get("/exports/full-backup")
def download_full_backup() -> FileResponse:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = temporary_download(".zip")
    try:
        create_full_backup(path)
    except ValueError as exc:
        path.unlink(missing_ok=True)
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="application/zip",
        filename=f"BOOKPILE-backup-{timestamp}.zip",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@app.get("/exports/books.csv")
def download_books_csv() -> FileResponse:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = temporary_download(".csv")
    try:
        write_books_csv(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=f"BOOKPILE-books-{timestamp}.csv",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@app.get("/exports/reading-sessions.csv")
def download_reading_sessions_csv() -> FileResponse:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    path = temporary_download(".csv")
    try:
        write_reading_sessions_csv(path)
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return FileResponse(
        path,
        media_type="text/csv; charset=utf-8",
        filename=f"BOOKPILE-reading-sessions-{timestamp}.csv",
        background=BackgroundTask(path.unlink, missing_ok=True),
    )


@app.post("/restore/inspect")
async def inspect_restore(
    backup: UploadFile = File(...),
) -> dict[str, Any]:
    path = temporary_download(".zip")
    size = 0
    try:
        with path.open("wb") as destination:
            while chunk := await backup.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_BACKUP_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail="Backup ZIP must be 1 GB or smaller",
                    )
                destination.write(chunk)
        try:
            return stage_restore(path)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        path.unlink(missing_ok=True)


@app.post("/restore/{token}")
def confirm_restore(token: str) -> dict[str, Any]:
    try:
        return perform_restore(token)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.get("/stats", response_model=Stats)
def stats() -> dict[str, int]:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(DISTINCT b.id) AS total,
                SUM(CASE WHEN b.status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN b.status = 'CURRENTLY_READING' AND NOT EXISTS (
                    SELECT 1 FROM reading_sessions rs
                    WHERE rs.book_id = b.id AND rs.state = 'COMPLETED'
                ) THEN 1 ELSE 0 END) AS currently_reading,
                SUM(CASE WHEN b.status = 'CURRENTLY_READING' AND EXISTS (
                    SELECT 1 FROM reading_sessions rs
                    WHERE rs.book_id = b.id AND rs.state = 'COMPLETED'
                ) THEN 1 ELSE 0 END) AS currently_rereading,
                SUM(CASE WHEN EXISTS (
                    SELECT 1 FROM reading_sessions rs
                    WHERE rs.book_id = b.id AND rs.state = 'COMPLETED'
                ) THEN 1 ELSE 0 END) AS read
            FROM books b
            """
        ).fetchone()
    return {
        key: row[key] or 0
        for key in (
            "total",
            "pending",
            "currently_reading",
            "currently_rereading",
            "read",
        )
    }


@app.get("/metadata-options")
def metadata_options() -> dict[str, list[str]]:
    fields = {
        "languages": "language",
        "publishers": "publisher",
        "series_names": "series_name",
        "fiction_categories": "fiction_category",
        "bindings": "binding",
        "publication_types": "publication_type",
    }
    with connect() as connection:
        options = {
            key: [
                row[0]
                for row in connection.execute(
                    f"""
                    SELECT DISTINCT {column}
                    FROM books
                    WHERE {column} IS NOT NULL AND trim({column}) <> ''
                    ORDER BY {column} COLLATE NOCASE
                    """
                ).fetchall()
            ]
            for key, column in fields.items()
        }
        genre_values = [
            row[0]
            for row in connection.execute(
                """
                SELECT genre_text
                FROM books
                WHERE genre_text IS NOT NULL AND trim(genre_text) <> ''
                """
            ).fetchall()
        ]
    genres = sorted(
        {
            genre.strip()
            for value in genre_values
            for genre in value.split(",")
            if genre.strip()
        },
        key=str.casefold,
    )
    return {**options, "genres": genres}


@app.get("/books", response_model=list[Book])
def list_books(
    book_id: int | None = None,
    book_status: BookStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
    sort_by: Literal[
        "title",
        "author",
        "physical",
        "acquisition_date",
        "reading_started_date",
        "read_date",
        "created_at",
    ] = "title",
    sort_order: Literal["asc", "desc"] = "asc",
    bookcase_id: int | None = None,
    shelf_id: int | None = None,
    container_id: int | None = None,
    date_field: Literal[
        "acquisition_date",
        "reading_started_date",
        "read_date",
    ] = "acquisition_date",
    date_from: date | None = None,
    date_to: date | None = None,
    include_unknown_dates: bool = False,
    include_unknown_sort_dates: bool = False,
    quick_view: Literal[
        "missing_finished",
        "original_collection",
    ]
    | None = None,
    catalogue_check: Literal[
        "missing_started",
        "missing_end",
        "no_location",
        "no_cover",
        "missing_metadata",
        "missing_isbn",
        "missing_page_count",
        "missing_publisher",
        "missing_current_ed_year",
        "missing_original_publication_year",
        "missing_language",
        "missing_fiction_category",
        "missing_binding",
        "missing_publication_type",
        "missing_genre",
    ]
    | None = None,
    isbn: str | None = Query(default=None, max_length=40),
    language: list[str] = Query(default=[]),
    genre: list[str] = Query(default=[]),
    publisher: list[str] = Query(default=[]),
    fiction_category: list[FictionCategory] = Query(default=[]),
    binding: list[Binding] = Query(default=[]),
    publication_type: list[PublicationType] = Query(default=[]),
    series_name: list[str] = Query(default=[]),
    series_state: Literal["ANY", "YES", "NO"] = "ANY",
    author_structure: Literal["ANY", "SINGLE", "MULTIPLE"] = "ANY",
    reading_activity: Literal["ANY", "INITIAL", "REREADING"] = "ANY",
    page_min: int | None = Query(default=None, ge=1),
    page_max: int | None = Query(default=None, ge=1),
    publication_year_field: Literal[
        "current_ed_year", "original_publication_year"
    ] = "current_ed_year",
    publication_year_min: int | None = Query(default=None, ge=1000, le=9999),
    publication_year_max: int | None = Query(default=None, ge=1000, le=9999),
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="Date from must be earlier than or equal to date to",
        )
    if book_id is not None:
        where.append("b.id = ?")
        params.append(book_id)
    if book_status:
        where.append("b.status = ?")
        params.append(book_status.value)
    if reading_activity == "INITIAL":
        where.append(
            """b.status = 'CURRENTLY_READING' AND NOT EXISTS (
                SELECT 1 FROM reading_sessions rs
                WHERE rs.book_id = b.id AND rs.state = 'COMPLETED'
            )"""
        )
    elif reading_activity == "REREADING":
        where.append(
            """b.status = 'CURRENTLY_READING' AND EXISTS (
                SELECT 1 FROM reading_sessions rs
                WHERE rs.book_id = b.id AND rs.state = 'COMPLETED'
            )"""
        )
    if search and search.strip():
        searchable_columns = ("b.title", "b.author", "b.series_name")
        where.append(
            "(" + " OR ".join(f"{column} LIKE ?" for column in searchable_columns)
            + " OR EXISTS (SELECT 1 FROM book_authors ba "
            "WHERE ba.book_id = b.id AND ba.name LIKE ?))"
        )
        term = f"%{search.strip()}%"
        params.extend(term for _ in range(len(searchable_columns) + 1))
    if bookcase_id is not None:
        where.append("bc.id = ?")
        params.append(bookcase_id)
    if shelf_id is not None:
        where.append("s.id = ?")
        params.append(shelf_id)
    if container_id is not None:
        where.append("c.id = ?")
        params.append(container_id)
    if quick_view == "missing_finished":
        where.append(
            "EXISTS (SELECT 1 FROM reading_sessions rs WHERE rs.book_id = b.id AND rs.dates_unknown = 1)"
        )
    elif quick_view == "original_collection":
        where.append("b.is_original_collection = 1")
    if catalogue_check == "missing_started":
        where.append(
            """
            (
                b.status = 'READ'
                AND b.reading_started_date IS NULL
                AND b.read_date IS NOT NULL
            )
            """
        )
    elif catalogue_check == "missing_end":
        where.append(
            """
            (
                b.status = 'READ'
                AND b.reading_started_date IS NOT NULL
                AND b.read_date IS NULL
            )
            """
        )
    elif catalogue_check == "no_location":
        where.append("b.container_id IS NULL")
    elif catalogue_check == "no_cover":
        where.append("(b.cover_filename IS NULL OR b.cover_filename = '')")
    elif catalogue_check == "missing_metadata":
        where.append(
            """
            (
                (b.isbn_10 IS NULL AND b.isbn_13 IS NULL)
                OR b.page_count IS NULL
                OR b.publisher IS NULL OR trim(b.publisher) = ''
                OR b.current_ed_year IS NULL
                OR b.original_publication_year IS NULL
                OR b.language IS NULL OR trim(b.language) = ''
                OR b.fiction_category IS NULL
                OR b.binding IS NULL
                OR b.publication_type IS NULL
                OR b.genre_text IS NULL OR trim(b.genre_text) = ''
            )
            """
        )
    elif catalogue_check == "missing_isbn":
        where.append("(b.isbn_10 IS NULL AND b.isbn_13 IS NULL)")
    elif catalogue_check == "missing_page_count":
        where.append("b.page_count IS NULL")
    elif catalogue_check == "missing_publisher":
        where.append("(b.publisher IS NULL OR trim(b.publisher) = '')")
    elif catalogue_check == "missing_current_ed_year":
        where.append("b.current_ed_year IS NULL")
    elif catalogue_check == "missing_original_publication_year":
        where.append("b.original_publication_year IS NULL")
    elif catalogue_check == "missing_language":
        where.append("(b.language IS NULL OR trim(b.language) = '')")
    elif catalogue_check == "missing_fiction_category":
        where.append("b.fiction_category IS NULL")
    elif catalogue_check == "missing_binding":
        where.append("b.binding IS NULL")
    elif catalogue_check == "missing_publication_type":
        where.append("b.publication_type IS NULL")
    elif catalogue_check == "missing_genre":
        where.append("(b.genre_text IS NULL OR trim(b.genre_text) = '')")
    metadata_filter_conditions(
        where,
        params,
        isbn=isbn,
        languages=language,
        genres=genre,
        publishers=publisher,
        fiction_categories=fiction_category,
        bindings=binding,
        publication_types=publication_type,
        series_names=series_name,
        series_state=series_state,
        author_structure=author_structure,
        page_min=page_min,
        page_max=page_max,
        publication_year_field=publication_year_field,
        publication_year_min=publication_year_min,
        publication_year_max=publication_year_max,
    )
    date_conditions: list[str] = []
    if date_field == "acquisition_date":
        if date_from is not None:
            date_conditions.append("b.acquisition_date >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            date_conditions.append("b.acquisition_date <= ?")
            params.append(date_to.isoformat())
        if date_conditions:
            date_clause = " AND ".join(date_conditions)
            where.append(
                f"(({date_clause}) OR b.acquisition_date IS NULL)"
                if include_unknown_dates else f"({date_clause})"
            )
    elif date_from is not None or date_to is not None:
        session_field = (
            "started_date" if date_field == "reading_started_date" else "finished_date"
        )
        session_conditions = ["rs.book_id = b.id"]
        if date_from is not None:
            session_conditions.append(f"rs.{session_field} >= ?")
            params.append(date_from.isoformat())
        if date_to is not None:
            session_conditions.append(f"rs.{session_field} <= ?")
            params.append(date_to.isoformat())
        session_match = "EXISTS (SELECT 1 FROM reading_sessions rs WHERE " + " AND ".join(session_conditions) + ")"
        if include_unknown_dates:
            session_match += " OR EXISTS (SELECT 1 FROM reading_sessions ru WHERE ru.book_id = b.id AND ru.dates_unknown = 1)"
        where.append(f"({session_match})")
    if (
        sort_by
        in {"acquisition_date", "reading_started_date", "read_date"}
        and not include_unknown_sort_dates
    ):
        where.append(f"b.{sort_by} IS NOT NULL")

    query = BOOK_SELECT
    if where:
        query += " WHERE " + " AND ".join(where)

    direction = "ASC" if sort_order == "asc" else "DESC"
    if sort_by == "physical":
        physical_columns = [
            "CASE WHEN b.container_id IS NULL THEN 1 ELSE 0 END ASC",
            f"bc.name COLLATE NOCASE {direction}",
            f"s.shelf_number {direction}",
            f"CASE c.layer WHEN 'BACKGROUND' THEN 0 ELSE 1 END {direction}",
            f"CASE c.container_type WHEN 'ROW' THEN 0 ELSE 1 END {direction}",
            f"c.container_number {direction}",
            f"b.position {direction}",
            f"b.title COLLATE NOCASE {direction}",
        ]
        query += " ORDER BY " + ", ".join(physical_columns)
    elif sort_by in {
        "acquisition_date",
        "reading_started_date",
        "read_date",
    }:
        unknown_direction = "ASC" if sort_order == "asc" else "DESC"
        query += (
            f" ORDER BY CASE WHEN b.{sort_by} IS NULL THEN 0 ELSE 1 END"
            f" {unknown_direction},"
            f" b.{sort_by} {direction}, b.title COLLATE NOCASE ASC"
        )
    elif sort_by == "author":
        query += (
            f" ORDER BY b.author COLLATE NOCASE {direction},"
            f" b.title COLLATE NOCASE {direction}"
        )
    elif sort_by == "created_at":
        query += (
            f" ORDER BY b.created_at {direction},"
            " b.title COLLATE NOCASE ASC"
        )
    else:
        query += (
            f" ORDER BY b.title COLLATE NOCASE {direction},"
            f" b.author COLLATE NOCASE {direction}"
        )

    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [serialize_book(row) for row in rows]


@app.post("/books", response_model=Book, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate) -> dict[str, Any]:
    container_id, position = location_values(payload)
    acquisition_date = (
        None if payload.is_original_collection else payload.acquisition_date
    )
    reading_started_date = payload.reading_started_date
    read_date = payload.read_date
    is_read_date_unknown = payload.is_read_date_unknown
    if payload.status == BookStatus.currently_reading:
        reading_started_date = reading_started_date or max(
            value for value in (date.today(), acquisition_date) if value is not None
        )
        is_read_date_unknown = False
    elif payload.status == BookStatus.read:
        if is_read_date_unknown or (
            reading_started_date is None and read_date is None
        ):
            reading_started_date = None
            read_date = None
            is_read_date_unknown = True
        else:
            if reading_started_date is None or read_date is None:
                raise HTTPException(
                    status_code=422,
                    detail="Completed readings require both dates or neither date",
                )
    else:
        is_read_date_unknown = False
    validate_book_dates(acquisition_date, reading_started_date, read_date)
    try:
        with connect() as connection:
            if container_id is not None and position is not None:
                connection.execute("BEGIN IMMEDIATE")
                shifting_down = payload.shift_direction.value == "DOWN"
                comparison = "<=" if shifting_down else ">="
                ordering = "DESC" if shifting_down else "ASC"
                occupied_rows = connection.execute(
                    f"""
                    SELECT id, title, author, position
                    FROM books
                    WHERE container_id = ? AND position {comparison} ?
                    ORDER BY position {ordering}
                    """,
                    (container_id, position),
                ).fetchall()
                if occupied_rows and occupied_rows[0]["position"] == position:
                    contiguous = []
                    expected_position = position
                    for row in occupied_rows:
                        if row["position"] != expected_position:
                            break
                        contiguous.append(row)
                        expected_position += -1 if shifting_down else 1

                    shift_possible = not (
                        shifting_down and contiguous[-1]["position"] == 1
                    )

                    if not payload.shift_existing:
                        occupant = contiguous[0]
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "POSITION_OCCUPIED",
                                "message": (
                                    f'Position {position} is occupied by '
                                    f'“{occupant["title"]}”'
                                ),
                                "occupant": {
                                    "id": occupant["id"],
                                    "title": occupant["title"],
                                    "author": occupant["author"],
                                },
                                "container_id": container_id,
                                "position": position,
                                "shift_count": len(contiguous),
                                "last_position": contiguous[-1]["position"],
                                "shift_direction": payload.shift_direction.value,
                                "shift_possible": shift_possible,
                            },
                        )

                    if not shift_possible:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "code": "POSITION_SHIFT_BLOCKED",
                                "message": (
                                    "Cannot make room downward because the "
                                    "occupied sequence reaches position 1"
                                ),
                                "container_id": container_id,
                                "position": position,
                                "shift_direction": payload.shift_direction.value,
                            },
                        )

                    for row in reversed(contiguous):
                        connection.execute(
                            """
                            UPDATE books
                            SET position = ?, updated_at = CURRENT_TIMESTAMP
                            WHERE id = ?
                            """,
                            (
                                row["position"] + (-1 if shifting_down else 1),
                                row["id"],
                            ),
                        )

            cursor = connection.execute(
                """
                INSERT INTO books (
                    title, author, has_multiple_authors, isbn_10, isbn_13,
                    subtitle, page_count, publisher, current_ed_year,
                    original_publication_year, language, edition_number,
                    fiction_category, binding, publication_type, genre_text,
                    series_name, series_volume,
                    status, goodreads_url, notes,
                    acquisition_date, reading_started_date, read_date,
                    is_read_date_unknown, is_original_collection,
                    container_id, position
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    payload.title,
                    payload.author if not payload.has_multiple_authors else "Multiple authors",
                    0,
                    payload.isbn_10,
                    payload.isbn_13,
                    payload.subtitle,
                    payload.page_count,
                    payload.publisher,
                    payload.current_ed_year,
                    payload.original_publication_year,
                    payload.language,
                    payload.edition_number,
                    payload.fiction_category.value if payload.fiction_category else None,
                    payload.binding.value if payload.binding else None,
                    payload.publication_type.value if payload.publication_type else None,
                    payload.genre_text,
                    payload.series_name,
                    payload.series_volume,
                    payload.status.value,
                    str(payload.goodreads_url) if payload.goodreads_url else None,
                    payload.notes,
                    (
                        acquisition_date.isoformat()
                        if acquisition_date
                        else None
                    ),
                    (
                        reading_started_date.isoformat()
                        if reading_started_date
                        else None
                    ),
                    read_date.isoformat() if read_date else None,
                    int(is_read_date_unknown),
                    int(payload.is_original_collection),
                    container_id,
                    position,
                ),
            )
            book_id = cursor.lastrowid
            if payload.has_multiple_authors:
                connection.executemany(
                    """
                    INSERT INTO book_authors (book_id, position, name)
                    VALUES (?, ?, ?)
                    """,
                    [
                        (book_id, index, name)
                        for index, name in enumerate(payload.structured_authors, 1)
                    ],
                )
                connection.execute(
                    """
                    UPDATE books
                    SET has_multiple_authors = 1,
                        author = 'Multiple authors',
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (book_id,),
                )
            if payload.status == BookStatus.currently_reading:
                start_reading(connection, book_id, reading_started_date)
            elif payload.status == BookStatus.read:
                add_historical_reading(
                    connection,
                    book_id,
                    started=reading_started_date,
                    finished=read_date,
                    dates_unknown=is_read_date_unknown,
                )
    except ReadingSessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return fetch_book(book_id)


@app.patch("/books/{book_id}", response_model=Book)
def update_book(book_id: int, payload: BookUpdate) -> dict[str, Any]:
    existing = fetch_book(book_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return existing

    structured_authors = changes.pop("structured_authors", None)
    author_structure_touched = bool(
        {"has_multiple_authors", "author", "structured_authors"}
        & payload.model_fields_set
    )
    next_multiple_authors = bool(
        changes.get("has_multiple_authors", existing["has_multiple_authors"])
    )
    next_author = changes.get("author", existing["author"])
    next_structured_authors = (
        structured_authors
        if "structured_authors" in payload.model_fields_set
        else existing["structured_authors"]
    )
    if next_multiple_authors:
        if next_author != "Multiple authors":
            raise HTTPException(
                status_code=422,
                detail="Multiple-author books require author = Multiple authors",
            )
        if len(next_structured_authors) < 2:
            raise HTTPException(
                status_code=422,
                detail="Multiple-author books require at least two authors",
            )
    else:
        if existing["has_multiple_authors"] and not next_multiple_authors:
            if "author" not in payload.model_fields_set or next_author == "Multiple authors":
                raise HTTPException(
                    status_code=422,
                    detail=(
                        "Converting to a single author requires a new author value"
                    ),
                )
        next_structured_authors = []
    if author_structure_touched:
        changes["has_multiple_authors"] = int(next_multiple_authors)
        changes["author"] = next_author

    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    if "author" in changes and changes["author"] is not None:
        changes["author"] = changes["author"].strip()
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
    for enum_field in ("fiction_category", "binding", "publication_type"):
        if enum_field in changes and changes[enum_field] is not None:
            changes[enum_field] = changes[enum_field].value
    if "goodreads_url" in changes and changes["goodreads_url"] is not None:
        changes["goodreads_url"] = str(changes["goodreads_url"])
    for date_field in (
        "acquisition_date",
        "reading_started_date",
        "read_date",
    ):
        if date_field in changes and changes[date_field] is not None:
            changes[date_field] = changes[date_field].isoformat()
    if "is_original_collection" in changes:
        changes["is_original_collection"] = int(
            changes["is_original_collection"]
        )
    if "is_read_date_unknown" in changes:
        changes["is_read_date_unknown"] = int(
            changes["is_read_date_unknown"]
        )
    if changes.get("is_original_collection"):
        changes["acquisition_date"] = None
    elif changes.get("acquisition_date") is not None:
        changes["is_original_collection"] = 0

    location_touched = {"container_id", "position"} & payload.model_fields_set
    if location_touched:
        container_id = changes.get("container_id", existing["container_id"])
        position = changes.get("position", existing["position"])
        if (container_id is None) != (position is None):
            raise HTTPException(
                status_code=422,
                detail="Container and position must be supplied together",
            )
        changes["container_id"] = container_id
        changes["position"] = position

    next_status = changes.get("status", existing["status"])
    next_read_date_unknown = bool(
        changes.get(
            "is_read_date_unknown",
            existing["is_read_date_unknown"],
        )
    )
    if (
        {"reading_started_date", "read_date"} & payload.model_fields_set
        and "is_read_date_unknown" not in payload.model_fields_set
    ):
        next_read_date_unknown = False
        changes["is_read_date_unknown"] = 0
    if next_status == BookStatus.currently_reading.value:
        changes["is_read_date_unknown"] = 0
        if changes.get(
            "reading_started_date", existing["reading_started_date"]
        ) is None:
            next_acquisition = parsed_date(
                changes.get("acquisition_date", existing["acquisition_date"])
            )
            changes["reading_started_date"] = max(
                value
                for value in (date.today(), next_acquisition)
                if value is not None
            ).isoformat()
    elif next_status == BookStatus.read.value:
        next_started_value = changes.get(
            "reading_started_date", existing["reading_started_date"]
        )
        next_finished_value = changes.get("read_date", existing["read_date"])
        if next_started_value is None and next_finished_value is None:
            next_read_date_unknown = True
        if next_read_date_unknown:
            changes["reading_started_date"] = None
            changes["read_date"] = None
            changes["is_read_date_unknown"] = 1
        else:
            if next_started_value is None or next_finished_value is None:
                raise HTTPException(
                    status_code=422,
                    detail="Completed readings require both dates or neither date",
                )
    else:
        changes["is_read_date_unknown"] = 0

    if changes.get("read_date") is not None:
        changes["is_read_date_unknown"] = 0

    validate_book_dates(
        parsed_date(changes.get("acquisition_date", existing["acquisition_date"])),
        parsed_date(
            changes.get(
                "reading_started_date",
                existing["reading_started_date"],
            )
        ),
        parsed_date(changes.get("read_date", existing["read_date"])),
    )

    assignments = ", ".join(f"{column} = ?" for column in changes)
    values = list(changes.values())
    projected_status = changes.get("status", existing["status"])
    projected_started = changes.get(
        "reading_started_date", existing["reading_started_date"]
    )
    projected_finished = changes.get("read_date", existing["read_date"])
    projected_unknown = bool(
        changes.get("is_read_date_unknown", existing["is_read_date_unknown"])
    )
    lifecycle_changed = (
        projected_status != existing["status"]
        or projected_started != existing["reading_started_date"]
        or projected_finished != existing["read_date"]
        or projected_unknown != bool(existing["is_read_date_unknown"])
    )
    try:
        with connect() as connection:
            if author_structure_touched:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "UPDATE books SET has_multiple_authors = 0 WHERE id = ?",
                    (book_id,),
                )
                connection.execute(
                    "DELETE FROM book_authors WHERE book_id = ?", (book_id,)
                )
                if next_multiple_authors:
                    connection.executemany(
                        """
                        INSERT INTO book_authors (book_id, position, name)
                        VALUES (?, ?, ?)
                        """,
                        [
                            (book_id, index, name)
                            for index, name in enumerate(next_structured_authors, 1)
                        ],
                    )
            next_container_id = changes.get("container_id", existing["container_id"])
            next_position = changes.get("position", existing["position"])
            location_changed = (
                next_container_id != existing["container_id"]
                or next_position != existing["position"]
            )
            if location_changed:
                if not connection.in_transaction:
                    connection.execute("BEGIN IMMEDIATE")
                if next_container_id is not None and next_position is not None:
                    ensure_container_exists(connection, next_container_id)
                connection.execute(
                    """
                    UPDATE books
                    SET container_id = NULL, position = NULL, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (book_id,),
                )
                close_position_gap(
                    connection,
                    existing["container_id"],
                    existing["position"],
                )
                if next_container_id is not None and next_position is not None:
                    make_room_for_position(
                        connection,
                        next_container_id,
                        next_position,
                    )
                connection.execute(
                    f"UPDATE books SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (*values, book_id),
                )
            else:
                connection.execute(
                    f"UPDATE books SET {assignments}, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (*values, book_id),
                )
            if lifecycle_changed:
                apply_projected_reading_values(
                    connection,
                    book_id,
                    status=projected_status,
                    started=parsed_date(projected_started),
                    finished=parsed_date(projected_finished),
                    dates_unknown=projected_unknown,
                )
            else:
                sync_book_projection(connection, book_id)
    except ReadingSessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return fetch_book(book_id)


def _reading_session_change(book_id: int, operation) -> dict[str, Any]:
    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            operation(connection)
    except ReadingSessionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return fetch_book(book_id)


@app.post("/books/{book_id}/reading-sessions/start", response_model=Book)
def start_book_reading(book_id: int, payload: ReadingStartRequest) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: start_reading(connection, book_id, payload.started_date),
    )


@app.post("/books/{book_id}/reading-sessions/finish", response_model=Book)
def finish_book_reading(book_id: int, payload: ReadingFinishRequest) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: finish_reading(connection, book_id, payload.finished_date),
    )


@app.delete("/books/{book_id}/reading-sessions/active", response_model=Book)
def cancel_book_reading(book_id: int) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: cancel_active_reading(connection, book_id),
    )


@app.post("/books/{book_id}/reading-sessions", response_model=Book)
def create_book_reading_history(
    book_id: int, payload: ReadingHistoryCreate
) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: add_historical_reading(
            connection,
            book_id,
            started=payload.started_date,
            finished=payload.finished_date,
            dates_unknown=payload.dates_unknown,
        ),
    )


@app.patch("/books/{book_id}/reading-sessions/{session_id}", response_model=Book)
def update_book_reading_history(
    book_id: int, session_id: int, payload: ReadingHistoryUpdate
) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: update_session(
            connection,
            book_id,
            session_id,
            started=payload.started_date,
            finished=payload.finished_date,
            dates_unknown=payload.dates_unknown,
        ),
    )


@app.delete("/books/{book_id}/reading-sessions/{session_id}", response_model=Book)
def delete_book_reading_history(book_id: int, session_id: int) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: delete_session(connection, book_id, session_id),
    )


@app.delete("/books/{book_id}/reading-sessions", response_model=Book)
def clear_book_reading_history(book_id: int) -> dict[str, Any]:
    return _reading_session_change(
        book_id,
        lambda connection: delete_all_sessions(connection, book_id),
    )


@app.post("/books/{book_id}/move", response_model=Book)
def move_book(book_id: int, payload: BookMove) -> dict[str, Any]:
    moving = fetch_book(book_id)
    try:
        with connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            ensure_container_exists(connection, payload.container_id)
            connection.execute(
                "UPDATE books SET container_id = NULL, position = NULL WHERE id = ?",
                (book_id,),
            )
            close_position_gap(
                connection,
                moving["container_id"],
                moving["position"],
            )
            make_room_for_position(
                connection,
                payload.container_id,
                payload.position,
            )
            connection.execute(
                """
                UPDATE books
                SET container_id = ?, position = ?, updated_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (payload.container_id, payload.position, book_id),
            )
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return fetch_book(book_id)


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int) -> Response:
    existing = fetch_book(book_id)
    with connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        cursor = connection.execute("DELETE FROM books WHERE id = ?", (book_id,))
        close_position_gap(
            connection,
            existing["container_id"],
            existing["position"],
        )
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    delete_cover_file(existing["cover_filename"])
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/covers/{filename}")
def cover_image(filename: str) -> FileResponse:
    if Path(filename).name != filename:
        raise HTTPException(status_code=404, detail="Cover not found")
    path = covers_directory() / filename
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Cover not found")
    return FileResponse(
        path,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@app.post("/books/{book_id}/cover", response_model=Book)
async def upload_cover(
    book_id: int,
    cover: UploadFile = File(...),
) -> dict[str, Any]:
    existing = fetch_book(book_id)
    contents = await cover.read(MAX_COVER_BYTES + 1)
    if len(contents) > MAX_COVER_BYTES:
        raise HTTPException(
            status_code=413,
            detail="Cover image must be 12 MB or smaller",
        )

    try:
        with Image.open(BytesIO(contents)) as source:
            if source.format not in ALLOWED_COVER_FORMATS:
                raise HTTPException(
                    status_code=415,
                    detail="Use a JPEG, PNG, WebP, HEIC, or HEIF image",
                )
            image = ImageOps.exif_transpose(source)
            image.thumbnail(MAX_COVER_SIZE, Image.Resampling.LANCZOS)
            if image.mode == "RGBA":
                background = Image.new("RGB", image.size, "white")
                background.paste(image, mask=image.getchannel("A"))
                image = background
            elif image.mode != "RGB":
                image = image.convert("RGB")

            filename = f"{uuid4().hex}.webp"
            destination = covers_directory() / filename
            image.save(destination, "WEBP", quality=82, method=6)
    except HTTPException:
        raise
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise HTTPException(
            status_code=415,
            detail="The selected file is not a valid supported image",
        ) from exc

    with connect() as connection:
        connection.execute(
            """
            UPDATE books
            SET cover_filename = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (filename, book_id),
        )
    delete_cover_file(existing["cover_filename"])
    return fetch_book(book_id)


@app.delete("/books/{book_id}/cover", response_model=Book)
def remove_cover(book_id: int) -> dict[str, Any]:
    existing = fetch_book(book_id)
    with connect() as connection:
        connection.execute(
            """
            UPDATE books
            SET cover_filename = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (book_id,),
        )
    delete_cover_file(existing["cover_filename"])
    return fetch_book(book_id)


@app.get("/library")
def library() -> list[dict[str, Any]]:
    with connect() as connection:
        bookcases = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM bookcases ORDER BY name COLLATE NOCASE"
            )
        ]
        shelves = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM shelves ORDER BY bookcase_id, shelf_number"
            )
        ]
        containers = [
            dict(row)
            for row in connection.execute(
                """
                SELECT c.*, COUNT(b.id) AS book_count
                FROM containers c
                LEFT JOIN books b ON b.container_id = c.id
                GROUP BY c.id
                ORDER BY c.shelf_id, c.layer, c.container_type, c.container_number
                """
            )
        ]

    shelves_by_bookcase: dict[int, list[dict[str, Any]]] = {}
    containers_by_shelf: dict[int, list[dict[str, Any]]] = {}
    for container in containers:
        containers_by_shelf.setdefault(container["shelf_id"], []).append(container)
    for shelf in shelves:
        shelf["containers"] = containers_by_shelf.get(shelf["id"], [])
        shelves_by_bookcase.setdefault(shelf["bookcase_id"], []).append(shelf)
    for bookcase in bookcases:
        bookcase["shelves"] = shelves_by_bookcase.get(bookcase["id"], [])
    return bookcases


def default_bookcase_rect(name: str, index: int, total: int) -> dict[str, float]:
    normalized = name.casefold()
    if "office" in normalized:
        return {"x": 2, "y": 12, "width": 24, "height": 78}
    if "left side" in normalized:
        return {"x": 31, "y": 8, "width": 18, "height": 84}
    if "wall unit" in normalized and "top" in normalized:
        return {"x": 49, "y": 5, "width": 49, "height": 40}
    width = min(28.0, 92.0 / max(total, 1))
    return {
        "x": 3 + index * (width + 2),
        "y": 8,
        "width": width,
        "height": 72,
    }


def ensure_visual_layout(
    connection: sqlite3.Connection,
    bookcases: list[dict[str, Any]],
    shelves: list[dict[str, Any]],
    containers: list[dict[str, Any]],
) -> None:
    total = len(bookcases)
    for index, bookcase in enumerate(bookcases):
        rect = default_bookcase_rect(bookcase["name"], index, total)
        connection.execute(
            """
            INSERT OR IGNORE INTO visual_layout_items
                (item_type, item_id, x, y, width, height)
            VALUES ('BOOKCASE', ?, ?, ?, ?, ?)
            """,
            (
                bookcase["id"],
                rect["x"],
                rect["y"],
                rect["width"],
                rect["height"],
            ),
        )
    connection.execute(
        """
        INSERT OR IGNORE INTO visual_layout_items
            (item_type, item_id, x, y, width, height)
        VALUES ('OUTSIDE', 0, 54, 70, 28, 18)
        """
    )
    for shelf in shelves:
        connection.execute(
            """
            INSERT OR IGNORE INTO visual_shelf_layout (shelf_id, height_weight)
            VALUES (?, 1)
            """,
            (shelf["id"],),
        )
    containers_by_shelf_layer: dict[tuple[int, str], list[dict[str, Any]]] = {}
    for container in containers:
        containers_by_shelf_layer.setdefault(
            (container["shelf_id"], container["layer"]), []
        ).append(container)
    for group in containers_by_shelf_layer.values():
        gap = 3.0
        width = max(8.0, (100.0 - gap * (len(group) - 1)) / len(group))
        for index, container in enumerate(group):
            has_opposite_layer = any(
                candidate["shelf_id"] == container["shelf_id"]
                and candidate["layer"] != container["layer"]
                for candidate in containers
            )
            if not has_opposite_layer:
                y = 0.0
                height = 100.0
            elif container["layer"] == "BACKGROUND":
                y = 0.0
                height = 68.0
            else:
                y = 50.0
                height = 50.0
            connection.execute(
                """
                INSERT OR IGNORE INTO visual_container_layout
                    (container_id, x, y, width, height)
                VALUES (?, ?, ?, ?, ?)
                """,
                (container["id"], index * (width + gap), y, width, height),
            )


def fetch_visual_layout(connection: sqlite3.Connection) -> dict[str, Any]:
    items = connection.execute(
        """
        SELECT item_type, item_id, x, y, width, height
        FROM visual_layout_items
        ORDER BY item_type, item_id
        """
    ).fetchall()
    bookcases = []
    outside = {"x": 54, "y": 70, "width": 28, "height": 18}
    for row in items:
        rect = {
            key: row[key]
            for key in ("x", "y", "width", "height")
        }
        if row["item_type"] == "OUTSIDE":
            outside = rect
        else:
            bookcases.append({"id": row["item_id"], **rect})
    return {
        "bookcases": bookcases,
        "shelves": [
            {"id": row["shelf_id"], "height_weight": row["height_weight"]}
            for row in connection.execute(
                "SELECT * FROM visual_shelf_layout ORDER BY shelf_id"
            )
        ],
        "containers": [
            {
                "id": row["container_id"],
                "x": row["x"],
                "y": row["y"],
                "width": row["width"],
                "height": row["height"],
            }
            for row in connection.execute(
                "SELECT * FROM visual_container_layout ORDER BY container_id"
            )
        ],
        "outside": outside,
    }


@app.get("/library-map")
def library_map() -> dict[str, Any]:
    map_book_fields = """
        id, title, author, has_multiple_authors, isbn_10, isbn_13, subtitle, page_count,
        publisher, current_ed_year, original_publication_year, language,
        edition_number, fiction_category, binding, publication_type,
        genre_text, series_name, series_volume, status, container_id,
        position, acquisition_date, reading_started_date, read_date,
        (status = 'CURRENTLY_READING' AND EXISTS (
            SELECT 1 FROM reading_sessions rs
            WHERE rs.book_id = books.id AND rs.state = 'COMPLETED'
        )) AS is_rereading
    """
    map_authors_field = """
        COALESCE((
            SELECT json_group_array(ordered.name)
            FROM (
                SELECT name FROM book_authors
                WHERE book_id = books.id ORDER BY position
            ) ordered
        ), '[]') AS structured_authors_json
    """
    with connect() as connection:
        bookcases = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM bookcases ORDER BY name COLLATE NOCASE"
            )
        ]
        shelves = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM shelves ORDER BY bookcase_id, shelf_number"
            )
        ]
        containers = [
            dict(row)
            for row in connection.execute(
                """
                SELECT *
                FROM containers
                ORDER BY
                    shelf_id,
                    CASE layer WHEN 'BACKGROUND' THEN 0 ELSE 1 END,
                    CASE container_type WHEN 'ROW' THEN 0 ELSE 1 END,
                    container_number
                """
            )
        ]
        books = [
            dict(row)
            for row in connection.execute(
                """
                SELECT {map_book_fields}, {map_authors_field}
                FROM books
                WHERE container_id IS NOT NULL
                  AND status != 'CURRENTLY_READING'
                ORDER BY container_id, position
                """.format(
                    map_book_fields=map_book_fields,
                    map_authors_field=map_authors_field,
                )
            )
        ]
        outside_books = [
            dict(row)
            for row in connection.execute(
                """
                SELECT {map_book_fields}, {map_authors_field}
                FROM books
                WHERE status = 'CURRENTLY_READING'
                ORDER BY title COLLATE NOCASE
                """.format(
                    map_book_fields=map_book_fields,
                    map_authors_field=map_authors_field,
                )
            )
        ]
        ensure_visual_layout(connection, bookcases, shelves, containers)
        layout = fetch_visual_layout(connection)

    for book in [*books, *outside_books]:
        book["structured_authors"] = json.loads(
            book.pop("structured_authors_json", "[]")
        )

    books_by_container: dict[int, list[dict[str, Any]]] = {}
    for book in books:
        books_by_container.setdefault(book["container_id"], []).append(book)

    containers_by_shelf: dict[int, list[dict[str, Any]]] = {}
    for container in containers:
        container["books"] = books_by_container.get(container["id"], [])
        container["book_count"] = len(container["books"])
        container["status_counts"] = {
            "pending": sum(
                book["status"] == BookStatus.pending.value
                for book in container["books"]
            ),
            "reading": sum(
                book["status"] == BookStatus.currently_reading.value
                for book in container["books"]
            ),
            "read": sum(
                book["status"] == BookStatus.read.value
                for book in container["books"]
            ),
        }
        containers_by_shelf.setdefault(container["shelf_id"], []).append(container)

    shelves_by_bookcase: dict[int, list[dict[str, Any]]] = {}
    for shelf in shelves:
        shelf["containers"] = containers_by_shelf.get(shelf["id"], [])
        shelf["book_count"] = sum(
            container["book_count"] for container in shelf["containers"]
        )
        shelves_by_bookcase.setdefault(shelf["bookcase_id"], []).append(shelf)

    for bookcase in bookcases:
        bookcase["shelves"] = shelves_by_bookcase.get(bookcase["id"], [])
        bookcase["book_count"] = sum(
            shelf["book_count"] for shelf in bookcase["shelves"]
        )
    return {
        "bookcases": bookcases,
        "outside_books": outside_books,
        "layout": layout,
    }


@app.put("/visual-layout")
def update_visual_layout(payload: VisualLayoutUpdate) -> dict[str, Any]:
    for rect in [*payload.bookcases, payload.outside]:
        if rect.x + rect.width > 100 or rect.y + rect.height > 100:
            raise HTTPException(
                status_code=422,
                detail="Layout items must remain inside the canvas",
            )
    for container in payload.containers:
        if container.x + container.width > 100 or container.y + container.height > 100:
            raise HTTPException(
                status_code=422,
                detail="Containers must remain inside their shelf layer",
            )

    with connect() as connection:
        valid_bookcases = {
            row["id"] for row in connection.execute("SELECT id FROM bookcases")
        }
        valid_shelves = {
            row["id"] for row in connection.execute("SELECT id FROM shelves")
        }
        valid_containers = {
            row["id"] for row in connection.execute("SELECT id FROM containers")
        }
        if {item.id for item in payload.bookcases} != valid_bookcases:
            raise HTTPException(status_code=422, detail="Bookcase layout is incomplete")
        if {item.id for item in payload.shelves} != valid_shelves:
            raise HTTPException(status_code=422, detail="Shelf layout is incomplete")
        if {item.id for item in payload.containers} != valid_containers:
            raise HTTPException(status_code=422, detail="Container layout is incomplete")

        container_context = {
            row["id"]: (row["shelf_id"], row["layer"])
            for row in connection.execute(
                "SELECT id, shelf_id, layer FROM containers"
            )
        }
        grouped_containers: dict[
            tuple[int, str], list[VisualContainerLayout]
        ] = {}
        for item in payload.containers:
            grouped_containers.setdefault(container_context[item.id], []).append(item)
        for group in grouped_containers.values():
            for index, first in enumerate(group):
                for second in group[index + 1 :]:
                    overlap_width = min(
                        first.x + first.width,
                        second.x + second.width,
                    ) - max(first.x, second.x)
                    overlap_height = min(
                        first.y + first.height,
                        second.y + second.height,
                    ) - max(first.y, second.y)
                    if overlap_width > 0.0001 and overlap_height > 0.0001:
                        raise HTTPException(
                            status_code=422,
                            detail={
                                "code": "CONTAINER_LAYOUT_OVERLAP",
                                "message": (
                                    "Containers in the same shelf layer cannot "
                                    "overlap"
                                ),
                                "container_ids": [first.id, second.id],
                            },
                        )

        connection.execute(
            "DELETE FROM visual_layout_items WHERE item_type = 'BOOKCASE'"
        )
        connection.executemany(
            """
            INSERT INTO visual_layout_items
                (item_type, item_id, x, y, width, height)
            VALUES ('BOOKCASE', ?, ?, ?, ?, ?)
            """,
            [
                (item.id, item.x, item.y, item.width, item.height)
                for item in payload.bookcases
            ],
        )
        connection.execute(
            """
            INSERT OR REPLACE INTO visual_layout_items
                (item_type, item_id, x, y, width, height)
            VALUES ('OUTSIDE', 0, ?, ?, ?, ?)
            """,
            (
                payload.outside.x,
                payload.outside.y,
                payload.outside.width,
                payload.outside.height,
            ),
        )
        connection.execute("DELETE FROM visual_shelf_layout")
        connection.executemany(
            """
            INSERT INTO visual_shelf_layout (shelf_id, height_weight)
            VALUES (?, ?)
            """,
            [(item.id, item.height_weight) for item in payload.shelves],
        )
        connection.execute("DELETE FROM visual_container_layout")
        connection.executemany(
            """
            INSERT INTO visual_container_layout (container_id, x, y, width, height)
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (item.id, item.x, item.y, item.width, item.height)
                for item in payload.containers
            ],
        )
        return fetch_visual_layout(connection)


@app.post("/bookcases", status_code=status.HTTP_201_CREATED)
def create_bookcase(payload: BookcaseCreate) -> dict[str, Any]:
    try:
        with connect() as connection:
            cursor = connection.execute(
                "INSERT INTO bookcases (name, description) VALUES (?, ?)",
                (payload.name.strip(), payload.description),
            )
            row = connection.execute(
                "SELECT * FROM bookcases WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Bookcase name already exists") from exc
    return dict(row)


def interval_summary(
    rows: list[sqlite3.Row],
    start_field: str,
    end_field: str,
) -> dict[str, int | float | None]:
    durations: list[int] = []
    for row in rows:
        start = parsed_date(row[start_field])
        end = parsed_date(row[end_field])
        if start is not None and end is not None:
            durations.append((end - start).days + 1)
    return {
        "average_days": (
            round(statistics_module.mean(durations), 1) if durations else None
        ),
        "median_days": (
            round(float(statistics_module.median(durations)), 1)
            if durations
            else None
        ),
        "sample_size": len(durations),
        "excluded": len(rows) - len(durations),
    }


@app.get("/statistics")
def catalogue_statistics(
    year: int | None = Query(default=None, ge=1000, le=9999),
    isbn: str | None = Query(default=None, max_length=40),
    language: list[str] = Query(default=[]),
    genre: list[str] = Query(default=[]),
    publisher: list[str] = Query(default=[]),
    fiction_category: list[FictionCategory] = Query(default=[]),
    binding: list[Binding] = Query(default=[]),
    publication_type: list[PublicationType] = Query(default=[]),
    series_name: list[str] = Query(default=[]),
    series_state: Literal["ANY", "YES", "NO"] = "ANY",
    author_structure: Literal["ANY", "SINGLE", "MULTIPLE"] = "ANY",
    page_min: int | None = Query(default=None, ge=1),
    page_max: int | None = Query(default=None, ge=1),
    publication_year_field: Literal[
        "current_ed_year", "original_publication_year"
    ] = "current_ed_year",
    publication_year_min: int | None = Query(default=None, ge=1000, le=9999),
    publication_year_max: int | None = Query(default=None, ge=1000, le=9999),
) -> dict[str, Any]:
    where: list[str] = []
    params: list[Any] = []
    metadata_filter_conditions(
        where,
        params,
        isbn=isbn,
        languages=language,
        genres=genre,
        publishers=publisher,
        fiction_categories=fiction_category,
        bindings=binding,
        publication_types=publication_type,
        series_names=series_name,
        series_state=series_state,
        author_structure=author_structure,
        page_min=page_min,
        page_max=page_max,
        publication_year_field=publication_year_field,
        publication_year_min=publication_year_min,
        publication_year_max=publication_year_max,
    )
    query = """
        SELECT b.id, b.title, b.author, b.status, b.acquisition_date,
               b.reading_started_date, b.read_date, b.is_original_collection,
               b.page_count,
               EXISTS(SELECT 1 FROM reading_sessions rc
                      WHERE rc.book_id = b.id AND rc.state = 'COMPLETED')
                   AS has_completed_reading
        FROM books b
    """
    if where:
        query += " WHERE " + " AND ".join(where)
    with connect() as connection:
        rows = list(connection.execute(query, params).fetchall())
        book_ids = [row["id"] for row in rows]
        if book_ids:
            placeholders = ", ".join("?" for _ in book_ids)
            read_rows = list(connection.execute(
                f"""
                SELECT rs.id AS session_id, rs.book_id AS id, b.title, b.author,
                       b.page_count, rs.started_date AS reading_started_date,
                       rs.finished_date AS read_date, rs.dates_unknown,
                       rs.session_number
                FROM reading_sessions rs
                JOIN books b ON b.id = rs.book_id
                WHERE rs.state = 'COMPLETED' AND rs.book_id IN ({placeholders})
                ORDER BY rs.finished_date, rs.book_id, rs.session_number
                """,
                book_ids,
            ).fetchall())
        else:
            read_rows = []

    acquired_by_year: dict[int, int] = {}
    read_by_year: dict[int, int] = {}
    acquired_by_month = [0] * 12
    read_by_month = [0] * 12
    for row in rows:
        acquired = parsed_date(row["acquisition_date"])
        if acquired is not None:
            acquired_by_year[acquired.year] = acquired_by_year.get(acquired.year, 0) + 1
            if year == acquired.year:
                acquired_by_month[acquired.month - 1] += 1
    for row in read_rows:
        finished = parsed_date(row["read_date"])
        if finished is not None:
            read_by_year[finished.year] = read_by_year.get(finished.year, 0) + 1
            if year == finished.year:
                read_by_month[finished.month - 1] += 1
    pages_by_day: dict[date, float] = {}
    page_sample_size = 0
    single_day_estimates = 0
    per_book_reading_rates: list[dict[str, Any]] = []
    for row in read_rows:
        finished = parsed_date(row["read_date"])
        page_count = row["page_count"]
        if finished is None or page_count is None:
            continue
        started = parsed_date(row["reading_started_date"])
        if started is None:
            continue
        estimated_start = False
        if started > finished:
            started = finished
        duration = (finished - started).days + 1
        pages_per_day = page_count / duration
        current = started
        while current <= finished:
            pages_by_day[current] = pages_by_day.get(current, 0) + pages_per_day
            current += timedelta(days=1)
        page_sample_size += 1
        if year is None or finished.year == year:
            per_book_reading_rates.append(
                {
                    "id": row["id"],
                    "session_number": row["session_number"],
                    "title": row["title"],
                    "author": row["author"],
                    "page_count": page_count,
                    "reading_days": duration,
                    "pages_per_day": round(page_count / duration, 1),
                    "read_date": finished.isoformat(),
                    "estimated_start": estimated_start,
                }
            )

    pages_by_year: dict[int, float] = {}
    pages_by_month = [0.0] * 12
    for reading_day, pages in pages_by_day.items():
        pages_by_year[reading_day.year] = pages_by_year.get(reading_day.year, 0) + pages
        if year == reading_day.year:
            pages_by_month[reading_day.month - 1] += pages

    years = sorted({*acquired_by_year, *read_by_year, *pages_by_year})
    yearly = [
        {
            "year": item,
            "acquired": acquired_by_year.get(item, 0),
            "read": read_by_year.get(item, 0),
            "pages_read": round(pages_by_year.get(item, 0), 1),
        }
        for item in years
    ]
    monthly = [
        {
            "month": month,
            "acquired": acquired_by_month[month - 1],
            "read": read_by_month[month - 1],
            "pages_read": round(pages_by_month[month - 1], 1),
        }
        for month in range(1, 13)
    ]

    started_rows = [
        row
        for row in rows
        if row["status"] in {
            BookStatus.currently_reading.value,
            BookStatus.read.value,
        }
    ]
    if year is not None:
        period_start = date(year, 1, 1)
        period_end = date(year, 12, 31)
        if year == date.today().year:
            period_end = min(period_end, date.today())
    elif pages_by_day:
        period_start = min(pages_by_day)
        period_end = max(pages_by_day)
    else:
        period_start = None
        period_end = None
    period_pages = (
        sum(
            pages
            for reading_day, pages in pages_by_day.items()
            if period_start is not None
            and period_end is not None
            and period_start <= reading_day <= period_end
        )
        if period_start is not None and period_end is not None
        else 0
    )
    period_days = (
        (period_end - period_start).days + 1
        if period_start is not None and period_end is not None
        else 0
    )
    per_book_reading_rates.sort(
        key=lambda item: (-item["pages_per_day"], item["title"].casefold())
    )
    individual_rates = [
        item["pages_per_day"] for item in per_book_reading_rates
    ]
    rate_period_rows = [
        row
        for row in read_rows
        if year is None
        or (
            parsed_date(row["read_date"]) is not None
            and parsed_date(row["read_date"]).year == year
        )
    ]

    def group_summary(original: bool) -> dict[str, int]:
        group = [row for row in rows if bool(row["is_original_collection"]) is original]
        return {
            "total": len(group),
            "pending": sum(row["status"] == BookStatus.pending.value for row in group),
            "reading": sum(
                row["status"] == BookStatus.currently_reading.value for row in group
            ),
            "read": sum(bool(row["has_completed_reading"]) for row in group),
        }

    return {
        "selected_year": year,
        "available_years": years,
        "yearly": yearly,
        "monthly": monthly,
        "reading_rate": {
            "total_pages": round(period_pages, 1),
            "pages_per_week": (
                round(period_pages / period_days * 7, 1) if period_days else None
            ),
            "pages_per_month": (
                round(period_pages / period_days * (365.2425 / 12), 1)
                if period_days
                else None
            ),
            "sample_size": page_sample_size,
            "excluded": len(read_rows) - page_sample_size,
            "single_day_estimates": single_day_estimates,
            "average_per_book": (
                round(statistics_module.mean(individual_rates), 1)
                if individual_rates
                else None
            ),
            "median_per_book": (
                round(float(statistics_module.median(individual_rates)), 1)
                if individual_rates
                else None
            ),
            "per_book": per_book_reading_rates,
            "per_book_sample_size": len(per_book_reading_rates),
            "per_book_excluded": len(rate_period_rows) - len(per_book_reading_rates),
            "per_book_estimates": sum(
                item["estimated_start"] for item in per_book_reading_rates
            ),
        },
        "reading_sessions": {
            "completed": len(read_rows),
            "unique_books": len({row["id"] for row in read_rows}),
            "rereads": sum(row["session_number"] > 1 for row in read_rows),
        },
        "filtered_book_count": len(rows),
        "pending_duration": interval_summary(
            started_rows, "acquisition_date", "reading_started_date"
        ),
        "reading_duration": interval_summary(
            read_rows, "reading_started_date", "read_date"
        ),
        "original_collection": group_summary(True),
        "later_acquisitions": group_summary(False),
    }


@app.get("/suggestions")
def reading_suggestion(
    mode: Literal["random", "oldest", "waiting"] = "random",
    minimum_days: int = Query(default=365, ge=0, le=36500),
    exclude_id: list[int] = Query(default=[]),
    isbn: str | None = Query(default=None, max_length=40),
    language: list[str] = Query(default=[]),
    genre: list[str] = Query(default=[]),
    publisher: list[str] = Query(default=[]),
    fiction_category: list[FictionCategory] = Query(default=[]),
    binding: list[Binding] = Query(default=[]),
    publication_type: list[PublicationType] = Query(default=[]),
    series_name: list[str] = Query(default=[]),
    series_state: Literal["ANY", "YES", "NO"] = "ANY",
    author_structure: Literal["ANY", "SINGLE", "MULTIPLE"] = "ANY",
    page_min: int | None = Query(default=None, ge=1),
    page_max: int | None = Query(default=None, ge=1),
    publication_year_field: Literal[
        "current_ed_year", "original_publication_year"
    ] = "current_ed_year",
    publication_year_min: int | None = Query(default=None, ge=1000, le=9999),
    publication_year_max: int | None = Query(default=None, ge=1000, le=9999),
) -> dict[str, Any]:
    where = ["b.status = 'PENDING'"]
    params: list[Any] = []
    if mode in {"oldest", "waiting"}:
        where.append("b.acquisition_date IS NOT NULL")
    if mode == "waiting":
        cutoff = date.today() - timedelta(days=minimum_days)
        where.append("b.acquisition_date <= ?")
        params.append(cutoff.isoformat())
    if exclude_id:
        placeholders = ", ".join("?" for _ in exclude_id)
        where.append(f"b.id NOT IN ({placeholders})")
        params.extend(exclude_id)
    metadata_filter_conditions(
        where,
        params,
        isbn=isbn,
        languages=language,
        genres=genre,
        publishers=publisher,
        fiction_categories=fiction_category,
        bindings=binding,
        publication_types=publication_type,
        series_names=series_name,
        series_state=series_state,
        author_structure=author_structure,
        page_min=page_min,
        page_max=page_max,
        publication_year_field=publication_year_field,
        publication_year_min=publication_year_min,
        publication_year_max=publication_year_max,
    )

    order = "b.acquisition_date ASC, b.title COLLATE NOCASE ASC"
    if mode in {"random", "waiting"}:
        order = "RANDOM()"
    query = BOOK_SELECT + " WHERE " + " AND ".join(where)
    query += f" ORDER BY {order} LIMIT 1"
    with connect() as connection:
        row = connection.execute(query, params).fetchone()
    if row is None:
        raise HTTPException(
            status_code=404,
            detail="No unread books match this suggestion",
        )
    book = serialize_book(row)
    acquired = parsed_date(book["acquisition_date"])
    return {
        "book": book,
        "waiting_days": max(0, (date.today() - acquired).days) if acquired else None,
    }


@app.patch("/bookcases/{bookcase_id}")
def update_bookcase(
    bookcase_id: int, payload: BookcaseUpdate
) -> dict[str, Any]:
    try:
        with connect() as connection:
            exists = connection.execute(
                "SELECT 1 FROM bookcases WHERE id = ?", (bookcase_id,)
            ).fetchone()
            if exists is None:
                raise HTTPException(status_code=404, detail="Bookcase not found")
            connection.execute(
                "UPDATE bookcases SET name = ?, description = ? WHERE id = ?",
                (payload.name, payload.description, bookcase_id),
            )
            row = connection.execute(
                "SELECT * FROM bookcases WHERE id = ?", (bookcase_id,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Bookcase name already exists"
        ) from exc
    return dict(row)


@app.post("/shelves", status_code=status.HTTP_201_CREATED)
def create_shelf(payload: ShelfCreate) -> dict[str, Any]:
    try:
        with connect() as connection:
            cursor = connection.execute(
                "INSERT INTO shelves (bookcase_id, shelf_number) VALUES (?, ?)",
                (payload.bookcase_id, payload.shelf_number),
            )
            row = connection.execute(
                "SELECT * FROM shelves WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409, detail="Shelf already exists or bookcase is invalid"
        ) from exc
    return dict(row)


@app.patch("/shelves/{shelf_id}")
def update_shelf(shelf_id: int, payload: ShelfUpdate) -> dict[str, Any]:
    with connect() as connection:
        shelf = connection.execute(
            "SELECT * FROM shelves WHERE id = ?", (shelf_id,)
        ).fetchone()
        if shelf is None:
            raise HTTPException(status_code=404, detail="Shelf not found")
        if shelf["shelf_number"] != payload.shelf_number:
            collision = connection.execute(
                """
                SELECT id FROM shelves
                WHERE bookcase_id = ? AND shelf_number = ?
                """,
                (shelf["bookcase_id"], payload.shelf_number),
            ).fetchone()
            if collision is None:
                connection.execute(
                    "UPDATE shelves SET shelf_number = ? WHERE id = ?",
                    (payload.shelf_number, shelf_id),
                )
            else:
                temporary_number = connection.execute(
                    """
                    SELECT COALESCE(MAX(shelf_number), 0) + 1
                    FROM shelves WHERE bookcase_id = ?
                    """,
                    (shelf["bookcase_id"],),
                ).fetchone()[0]
                connection.execute(
                    "UPDATE shelves SET shelf_number = ? WHERE id = ?",
                    (temporary_number, shelf_id),
                )
                connection.execute(
                    "UPDATE shelves SET shelf_number = ? WHERE id = ?",
                    (shelf["shelf_number"], collision["id"]),
                )
                connection.execute(
                    "UPDATE shelves SET shelf_number = ? WHERE id = ?",
                    (payload.shelf_number, shelf_id),
                )
        row = connection.execute(
            "SELECT * FROM shelves WHERE id = ?", (shelf_id,)
        ).fetchone()
    return dict(row)


@app.post("/containers", status_code=status.HTTP_201_CREATED)
def create_container(payload: ContainerCreate) -> dict[str, Any]:
    try:
        with connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO containers (
                    shelf_id, container_type, layer, container_number
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    payload.shelf_id,
                    payload.container_type.value,
                    payload.layer.value,
                    payload.container_number,
                ),
            )
            row = connection.execute(
                "SELECT * FROM containers WHERE id = ?", (cursor.lastrowid,)
            ).fetchone()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(
            status_code=409,
            detail=(
                "This row or pile number already exists in the selected shelf/layer, "
                "or the shelf is invalid"
            ),
        ) from exc
    return dict(row)


@app.patch("/containers/{container_id}")
def update_container(
    container_id: int, payload: ContainerUpdate
) -> dict[str, Any]:
    with connect() as connection:
        container = connection.execute(
            "SELECT * FROM containers WHERE id = ?", (container_id,)
        ).fetchone()
        if container is None:
            raise HTTPException(status_code=404, detail="Container not found")
        if container["container_number"] != payload.container_number:
            context = (
                container["shelf_id"],
                container["container_type"],
                container["layer"],
            )
            collision = connection.execute(
                """
                SELECT id FROM containers
                WHERE shelf_id = ? AND container_type = ? AND layer = ?
                  AND container_number = ?
                """,
                (*context, payload.container_number),
            ).fetchone()
            if collision is None:
                connection.execute(
                    "UPDATE containers SET container_number = ? WHERE id = ?",
                    (payload.container_number, container_id),
                )
            else:
                temporary_number = connection.execute(
                    """
                    SELECT COALESCE(MAX(container_number), 0) + 1
                    FROM containers
                    WHERE shelf_id = ? AND container_type = ? AND layer = ?
                    """,
                    context,
                ).fetchone()[0]
                connection.execute(
                    "UPDATE containers SET container_number = ? WHERE id = ?",
                    (temporary_number, container_id),
                )
                connection.execute(
                    "UPDATE containers SET container_number = ? WHERE id = ?",
                    (container["container_number"], collision["id"]),
                )
                connection.execute(
                    "UPDATE containers SET container_number = ? WHERE id = ?",
                    (payload.container_number, container_id),
                )
        row = connection.execute(
            "SELECT * FROM containers WHERE id = ?", (container_id,)
        ).fetchone()
    return dict(row)


@app.delete("/containers/{container_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_container(container_id: int) -> Response:
    with connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM containers WHERE id = ?", (container_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Container not found")
        connection.execute(
            """
            UPDATE books
            SET container_id = NULL, position = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE container_id = ?
            """,
            (container_id,),
        )
        connection.execute("DELETE FROM containers WHERE id = ?", (container_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.delete("/shelves/{shelf_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_shelf(shelf_id: int) -> Response:
    with connect() as connection:
        exists = connection.execute(
            "SELECT 1 FROM shelves WHERE id = ?", (shelf_id,)
        ).fetchone()
        if exists is None:
            raise HTTPException(status_code=404, detail="Shelf not found")
        connection.execute(
            """
            UPDATE books
            SET container_id = NULL, position = NULL, updated_at = CURRENT_TIMESTAMP
            WHERE container_id IN (
                SELECT id FROM containers WHERE shelf_id = ?
            )
            """,
            (shelf_id,),
        )
        connection.execute("DELETE FROM shelves WHERE id = ?", (shelf_id,))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
