import os
import sqlite3
import tempfile
from contextlib import asynccontextmanager
from datetime import date, datetime
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

from .database import connect, database_path, init_database
from .exports import create_full_backup, write_books_csv
from .restore import MAX_BACKUP_BYTES, perform_restore, stage_restore
from .schemas import (
    Book,
    BookCreate,
    BookMove,
    BookStatus,
    BookUpdate,
    BookcaseCreate,
    ContainerCreate,
    ShelfCreate,
    Stats,
    VisualLayoutUpdate,
)


BOOK_SELECT = """
SELECT
    b.*,
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
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
                SUM(
                    CASE WHEN status = 'CURRENTLY_READING' THEN 1 ELSE 0 END
                ) AS currently_reading,
                SUM(CASE WHEN status = 'READ' THEN 1 ELSE 0 END) AS read
            FROM books
            """
        ).fetchone()
    return {
        key: row[key] or 0
        for key in ("total", "pending", "currently_reading", "read")
    }


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
    ]
    | None = None,
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
    if search and search.strip():
        where.append("(b.title LIKE ? OR b.author LIKE ?)")
        term = f"%{search.strip()}%"
        params.extend((term, term))
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
        where.append("(b.status = 'READ' AND b.read_date IS NULL)")
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
    date_conditions: list[str] = []
    if date_from is not None:
        date_conditions.append(f"b.{date_field} >= ?")
        params.append(date_from.isoformat())
    if date_to is not None:
        date_conditions.append(f"b.{date_field} <= ?")
        params.append(date_to.isoformat())
    if date_conditions:
        date_clause = " AND ".join(date_conditions)
        if include_unknown_dates:
            where.append(f"(({date_clause}) OR b.{date_field} IS NULL)")
        else:
            where.append(f"({date_clause})")
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
        if is_read_date_unknown:
            read_date = None
        else:
            read_date = read_date or max(
                value
                for value in (
                    date.today(),
                    acquisition_date,
                    reading_started_date,
                )
                if value is not None
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
                    title, author, status, goodreads_url, notes,
                    acquisition_date, reading_started_date, read_date,
                    is_read_date_unknown, is_original_collection,
                    container_id, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.title,
                    payload.author,
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
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return fetch_book(book_id)


@app.patch("/books/{book_id}", response_model=Book)
def update_book(book_id: int, payload: BookUpdate) -> dict[str, Any]:
    existing = fetch_book(book_id)
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return existing

    if "title" in changes and changes["title"] is not None:
        changes["title"] = changes["title"].strip()
    if "author" in changes and changes["author"] is not None:
        changes["author"] = changes["author"].strip()
    if "status" in changes and changes["status"] is not None:
        changes["status"] = changes["status"].value
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
    if next_status == BookStatus.currently_reading.value:
        changes["is_read_date_unknown"] = 0
        if (
            "reading_started_date" not in payload.model_fields_set
            and existing["reading_started_date"] is None
        ):
            next_acquisition = parsed_date(
                changes.get("acquisition_date", existing["acquisition_date"])
            )
            changes["reading_started_date"] = max(
                value
                for value in (date.today(), next_acquisition)
                if value is not None
            ).isoformat()
    elif next_status == BookStatus.read.value:
        if next_read_date_unknown:
            changes["read_date"] = None
            changes["is_read_date_unknown"] = 1
        elif (
            changes.get("read_date", existing["read_date"]) is None
            and (
                (
                    "status" in payload.model_fields_set
                    and existing["status"] != BookStatus.read.value
                )
                or (
                    "is_read_date_unknown" in payload.model_fields_set
                    and existing["is_read_date_unknown"]
                )
            )
        ):
            next_acquisition = parsed_date(
                changes.get("acquisition_date", existing["acquisition_date"])
            )
            next_started = parsed_date(
                changes.get(
                    "reading_started_date",
                    existing["reading_started_date"],
                )
            )
            changes["read_date"] = max(
                value
                for value in (date.today(), next_acquisition, next_started)
                if value is not None
            ).isoformat()
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
    try:
        with connect() as connection:
            next_container_id = changes.get("container_id", existing["container_id"])
            next_position = changes.get("position", existing["position"])
            location_changed = (
                next_container_id != existing["container_id"]
                or next_position != existing["position"]
            )
            if location_changed:
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
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return fetch_book(book_id)


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
                SELECT
                    id, title, status, container_id, position,
                    acquisition_date, reading_started_date, read_date
                FROM books
                WHERE container_id IS NOT NULL
                  AND status != 'CURRENTLY_READING'
                ORDER BY container_id, position
                """
            )
        ]
        outside_books = [
            dict(row)
            for row in connection.execute(
                """
                SELECT
                    id, title, status, container_id, NULL AS position,
                    acquisition_date, reading_started_date, read_date
                FROM books
                WHERE status = 'CURRENTLY_READING'
                ORDER BY title COLLATE NOCASE
                """
            )
        ]
        ensure_visual_layout(connection, bookcases, shelves, containers)
        layout = fetch_visual_layout(connection)

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
