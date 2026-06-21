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
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=422,
            detail="Date from must be earlier than or equal to date to",
        )
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
    if date_from is not None:
        where.append(f"b.{date_field} >= ?")
        params.append(date_from.isoformat())
    if date_to is not None:
        where.append(f"b.{date_field} <= ?")
        params.append(date_to.isoformat())

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
        query += (
            f" ORDER BY CASE WHEN b.{sort_by} IS NULL THEN 1 ELSE 0 END ASC,"
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
    reading_started_date = payload.reading_started_date
    read_date = payload.read_date
    if payload.status == BookStatus.currently_reading:
        container_id, position = None, None
        reading_started_date = reading_started_date or date.today()
    elif payload.status == BookStatus.read:
        read_date = read_date or date.today()
    try:
        with connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO books (
                    title, author, status, goodreads_url, notes,
                    acquisition_date, reading_started_date, read_date,
                    is_original_collection, container_id, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.title,
                    payload.author,
                    payload.status.value,
                    str(payload.goodreads_url) if payload.goodreads_url else None,
                    payload.notes,
                    (
                        payload.acquisition_date.isoformat()
                        if payload.acquisition_date
                        else None
                    ),
                    (
                        reading_started_date.isoformat()
                        if reading_started_date
                        else None
                    ),
                    read_date.isoformat() if read_date else None,
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
    if next_status == BookStatus.currently_reading.value:
        changes["container_id"] = None
        changes["position"] = None
        if (
            "reading_started_date" not in payload.model_fields_set
            and existing["reading_started_date"] is None
        ):
            changes["reading_started_date"] = date.today().isoformat()
    elif (
        next_status == BookStatus.read.value
        and "read_date" not in payload.model_fields_set
        and existing["read_date"] is None
    ):
        changes["read_date"] = date.today().isoformat()

    assignments = ", ".join(f"{column} = ?" for column in changes)
    values = list(changes.values())
    try:
        with connect() as connection:
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
    if moving["status"] == BookStatus.currently_reading.value:
        raise HTTPException(
            status_code=409,
            detail="A currently-reading book must remain outside the library map",
        )

    try:
        with connect() as connection:
            container_exists = connection.execute(
                "SELECT 1 FROM containers WHERE id = ?", (payload.container_id,)
            ).fetchone()
            if container_exists is None:
                raise HTTPException(status_code=404, detail="Container not found")

            occupant = connection.execute(
                """
                SELECT id
                FROM books
                WHERE container_id = ? AND position = ? AND id != ?
                """,
                (payload.container_id, payload.position, book_id),
            ).fetchone()
            if occupant and not payload.swap_if_occupied:
                raise HTTPException(status_code=409, detail="Position is already occupied")

            connection.execute(
                "UPDATE books SET container_id = NULL, position = NULL WHERE id = ?",
                (book_id,),
            )
            if occupant:
                connection.execute(
                    """
                    UPDATE books
                    SET container_id = ?, position = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE id = ?
                    """,
                    (
                        moving["container_id"],
                        moving["position"],
                        occupant["id"],
                    ),
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
        cursor = connection.execute("DELETE FROM books WHERE id = ?", (book_id,))
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
