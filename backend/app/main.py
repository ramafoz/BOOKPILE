import sqlite3
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from .database import connect, init_database
from .schemas import (
    Book,
    BookCreate,
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
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/stats", response_model=Stats)
def stats() -> dict[str, int]:
    with connect() as connection:
        row = connection.execute(
            """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = 'PENDING' THEN 1 ELSE 0 END) AS pending,
                SUM(CASE WHEN status = 'READ' THEN 1 ELSE 0 END) AS read
            FROM books
            """
        ).fetchone()
    return {key: row[key] or 0 for key in ("total", "pending", "read")}


@app.get("/books", response_model=list[Book])
def list_books(
    book_status: BookStatus | None = Query(default=None, alias="status"),
    search: str | None = Query(default=None, max_length=200),
) -> list[dict[str, Any]]:
    where: list[str] = []
    params: list[Any] = []
    if book_status:
        where.append("b.status = ?")
        params.append(book_status.value)
    if search and search.strip():
        where.append("(b.title LIKE ? OR b.author LIKE ?)")
        term = f"%{search.strip()}%"
        params.extend((term, term))

    query = BOOK_SELECT
    if where:
        query += " WHERE " + " AND ".join(where)
    query += " ORDER BY b.title COLLATE NOCASE, b.author COLLATE NOCASE"

    with connect() as connection:
        rows = connection.execute(query, params).fetchall()
    return [serialize_book(row) for row in rows]


@app.post("/books", response_model=Book, status_code=status.HTTP_201_CREATED)
def create_book(payload: BookCreate) -> dict[str, Any]:
    container_id, position = location_values(payload)
    try:
        with connect() as connection:
            cursor = connection.execute(
                """
                INSERT INTO books (
                    title, author, status, goodreads_url, notes, container_id, position
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    payload.title,
                    payload.author,
                    payload.status.value,
                    str(payload.goodreads_url) if payload.goodreads_url else None,
                    payload.notes,
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


@app.delete("/books/{book_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_book(book_id: int) -> Response:
    with connect() as connection:
        cursor = connection.execute("DELETE FROM books WHERE id = ?", (book_id,))
    if cursor.rowcount == 0:
        raise HTTPException(status_code=404, detail="Book not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


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
                SELECT * FROM containers
                ORDER BY shelf_id, layer, container_number
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
            detail="Container number already exists in this shelf/layer or shelf is invalid",
        ) from exc
    return dict(row)

