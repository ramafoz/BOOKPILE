from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Numeric, func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..cover_images import process_cover_image
from ..cover_storage import CoverStorage
from ..models import (
    Book,
    BookContributor,
    BookCover,
    Bookcase,
    Container,
    LibraryAuditEvent,
    Loan,
    PersonalBookRecord,
    ReadingSession,
    Shelf,
    VisualBookcaseLayout,
    VisualContainerLayout,
    VisualOutsideArea,
    VisualShelfLayout,
)
from .local_zip import CanonicalLocalV8Records
from .server_zip import CanonicalServerV1Records


LOCAL_WORLD_SCALE_MM = Decimal("25")


class LocalImportConflict(ValueError):
    pass


def _date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise LocalImportConflict(f"Invalid Local date: {value}") from exc


def _datetime(value: Any) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as exc:
        raise LocalImportConflict(f"Invalid Local timestamp: {value}") from exc
    return parsed.replace(tzinfo=parsed.tzinfo or UTC)


def _decimal(value: Any) -> Decimal:
    return Decimal(str(value))


def _world_rect(source: dict[str, Any]) -> tuple[Decimal, Decimal, Decimal, Decimal]:
    x = _decimal(source["x"]) * LOCAL_WORLD_SCALE_MM
    width = _decimal(source["width"]) * LOCAL_WORLD_SCALE_MM
    height = _decimal(source["height"]) * LOCAL_WORLD_SCALE_MM
    floor = (Decimal("100") - _decimal(source["y"]) - _decimal(source["height"])) * LOCAL_WORLD_SCALE_MM
    if width <= 0 or height <= 0:
        raise LocalImportConflict("Local map rectangles must have positive dimensions.")
    return x, floor, width, height


def _shelf_rectangles(
    source_shelves: list[dict[str, Any]],
    weights: dict[int, Decimal],
    width: Decimal,
    height: Decimal,
) -> dict[int, dict[str, Decimal | None]]:
    frame = width * Decimal("0.025")
    closure = height * Decimal("0.025")
    separator = max(Decimal("5"), width * Decimal("0.025"))
    count = len(source_shelves)
    available = height - closure * 2 - separator * max(0, count - 1)
    if count and available < Decimal("5") * count:
        raise LocalImportConflict("Local shelves cannot be represented safely inside their furniture.")
    total_weight = sum((weights.get(int(item["source_id"]), Decimal("1")) for item in source_shelves), Decimal("0"))
    if total_weight <= 0:
        raise LocalImportConflict("Local shelf weights must be positive.")
    cursor = height - closure
    result: dict[int, dict[str, Decimal | None]] = {}
    for index, source in enumerate(sorted(source_shelves, key=lambda item: int(item["shelf_number"]))):
        source_id = int(source["source_id"])
        shelf_height = available * weights.get(source_id, Decimal("1")) / total_weight
        floor = cursor - shelf_height
        result[source_id] = {
            "x_mm": frame,
            "floor_y_mm": floor,
            "width_mm": width - frame * 2,
            "height_mm": shelf_height,
            "frame": frame,
            "closure": closure,
            "separator": separator if index < count - 1 else None,
        }
        cursor = floor - (separator if index < count - 1 else Decimal("0"))
    return result


def consolidate_local_v8(
    *,
    session: Session,
    storage: CoverStorage,
    settings: Settings,
    records: CanonicalLocalV8Records,
    extracted: Path,
    library_id: UUID,
    reading_owner_user_id: UUID,
    actor_user_id: UUID,
) -> tuple[dict[str, int], list[str]]:
    """Stage all canonical records in the caller's transaction and private store."""
    existing_names = {
        name.casefold()
        for name in session.scalars(select(Bookcase.name).where(Bookcase.library_id == library_id))
    }
    conflicts = [str(item["name"]) for item in records.bookcases if str(item["name"]).casefold() in existing_names]
    if conflicts:
        raise LocalImportConflict(
            "Furniture names already exist in the destination: " + ", ".join(conflicts)
        )

    bookcase_ids = {int(item["source_id"]): uuid4() for item in records.bookcases}
    shelf_ids = {int(item["source_id"]): uuid4() for item in records.shelves}
    container_ids = {int(item["source_id"]): uuid4() for item in records.containers}
    book_ids = {int(item["source_id"]): uuid4() for item in records.books}
    session.add_all(
        [
            Bookcase(
                id=bookcase_ids[int(item["source_id"])],
                library_id=library_id,
                name=str(item["name"]),
                description=item["description"],
            )
            for item in records.bookcases
        ]
    )
    session.flush()
    session.add_all(
        [
            Shelf(
                id=shelf_ids[int(item["source_id"])],
                library_id=library_id,
                bookcase_id=bookcase_ids[int(item["source_bookcase_id"])],
                shelf_number=int(item["shelf_number"]),
            )
            for item in records.shelves
        ]
    )
    session.flush()
    session.add_all(
        [
            Container(
                id=container_ids[int(item["source_id"])],
                library_id=library_id,
                shelf_id=shelf_ids[int(item["source_shelf_id"])],
                container_type=str(item["container_type"]),
                layer=str(item["layer"]),
                container_number=int(item["container_number"]),
            )
            for item in records.containers
        ]
    )
    session.flush()

    book_rows: list[Book] = []
    for item in records.books:
        source_container = item["source_container_id"]
        book_rows.append(
            Book(
                id=book_ids[int(item["source_id"])],
                library_id=library_id,
                title=str(item["title"]),
                author=str(item["author"]),
                isbn_10=item["isbn_10"],
                isbn_13=item["isbn_13"],
                subtitle=item["subtitle"],
                page_count=item["page_count"],
                publisher=item["publisher"],
                current_ed_year=item["current_ed_year"],
                original_publication_year=item["original_publication_year"],
                language=item["language"],
                translation_status="UNKNOWN",
                edition_number=item["edition_number"],
                fiction_category=item["fiction_category"],
                binding=item["binding"],
                publication_type=item["publication_type"],
                genre_text=item["genre_text"],
                series_name=item["series_name"],
                series_volume=item["series_volume"],
                notes=item["notes"],
                acquisition_date=_date(item["acquisition_date"]),
                is_original_collection=bool(item["is_original_collection"]),
                container_id=container_ids[int(source_container)] if source_container is not None else None,
                position=int(item["position"]) if item["position"] is not None else None,
                created_at=_datetime(item["created_at"]),
                updated_at=_datetime(item["updated_at"]),
            )
        )
    session.add_all(book_rows)
    session.flush()

    session.add_all(
        [
            BookContributor(
                library_id=library_id,
                book_id=book_ids[int(item["source_book_id"])],
                role_code=str(item["role_code"]),
                position=int(item["position"]),
                name=str(item["name"]),
            )
            for item in records.contributors
        ]
    )
    session.add_all(
        [
            ReadingSession(
                library_id=library_id,
                book_id=book_ids[int(item["source_book_id"])],
                user_id=reading_owner_user_id,
                state=str(item["state"]),
                started_date=_date(item["started_date"]),
                finished_date=_date(item["finished_date"]),
                dates_unknown=bool(item["dates_unknown"]),
                created_at=_datetime(item["created_at"]),
                updated_at=_datetime(item["updated_at"]),
            )
            for item in records.readings
        ]
    )
    session.add_all(
        [
            Loan(
                library_id=library_id,
                book_id=book_ids[int(item["source_book_id"])],
                loaned_to=str(item["loaned_to"]),
                notes=item["notes"],
                state=str(item["state"]),
                loaned_date=_date(item["loaned_date"]),
                expected_return_date=_date(item["expected_return_date"]),
                returned_date=_date(item["returned_date"]),
                created_at=_datetime(item["created_at"]),
                updated_at=_datetime(item["updated_at"]),
            )
            for item in records.loans
        ]
    )
    session.add_all(
        [
            PersonalBookRecord(
                library_id=library_id,
                book_id=book_ids[int(item["source_id"])],
                user_id=reading_owner_user_id,
                goodreads_url=str(item["personal_goodreads_url"]).strip(),
            )
            for item in records.books
            if item["personal_goodreads_url"] and str(item["personal_goodreads_url"]).strip()
        ]
    )

    source_bookcases = {int(item["source_id"]): item for item in records.bookcases}
    source_shelves_by_case: dict[int, list[dict[str, Any]]] = {}
    for item in records.shelves:
        source_shelves_by_case.setdefault(int(item["source_bookcase_id"]), []).append(item)
    weights = {int(item["source_shelf_id"]): _decimal(item["height_weight"]) for item in records.shelf_layouts}
    layout_by_case = {int(item["source_bookcase_id"]): item for item in records.bookcase_layouts}
    generated_x = Decimal("0")
    shelf_geometry: dict[int, dict[str, Decimal | None]] = {}
    for source_id in sorted(source_bookcases):
        source_layout = layout_by_case.get(source_id)
        if source_layout is None:
            x, floor, width, height = generated_x, Decimal("0"), Decimal("800"), Decimal("2200")
            generated_x += Decimal("900")
        else:
            x, floor, width, height = _world_rect(source_layout)
        frame = width * Decimal("0.025")
        closure = height * Decimal("0.025")
        separator = max(Decimal("5"), width * Decimal("0.025"))
        session.add(
            VisualBookcaseLayout(
                library_id=library_id,
                bookcase_id=bookcase_ids[source_id],
                x_mm=x,
                floor_y_mm=floor,
                width_mm=width,
                height_mm=height,
                shelf_direction="TOP_TO_BOTTOM",
                homogeneous_structure=True,
                frame_left_mm=frame,
                frame_right_mm=frame,
                top_closure_mm=closure,
                bottom_closure_mm=closure,
                separator_thickness_mm=separator,
            )
        )
        shelf_geometry.update(
            _shelf_rectangles(source_shelves_by_case.get(source_id, []), weights, width, height)
        )
    for source_id, geometry in shelf_geometry.items():
        session.add(
            VisualShelfLayout(
                library_id=library_id,
                shelf_id=shelf_ids[source_id],
                height_weight=weights.get(source_id, Decimal("1")),
                x_mm=geometry["x_mm"],
                floor_y_mm=geometry["floor_y_mm"],
                width_mm=geometry["width_mm"],
                height_mm=geometry["height_mm"],
                alignment="CENTER",
                offset_mm=Decimal("0"),
                width_source="FALLBACK",
                height_source="FALLBACK",
                open_top=False,
                left_frame_mm=geometry["frame"],
                right_frame_mm=geometry["frame"],
                top_closure_mm=geometry["closure"],
                bottom_board_mm=geometry["closure"],
                separator_after_mm=geometry["separator"],
                separator_anchor="BOTTOM",
                separator_height_mm=None,
                separator_source="FALLBACK" if geometry["separator"] is not None else None,
            )
        )
    for item in records.container_layouts:
        support_source = item["source_support_container_id"]
        session.add(
            VisualContainerLayout(
                library_id=library_id,
                container_id=container_ids[int(item["source_container_id"])],
                x=_decimal(item["x"]),
                y=_decimal(item["y"]),
                width=_decimal(item["width"]),
                height=_decimal(item["height"]),
                row_anchor=str(item["row_anchor"]),
                support_kind="CONTAINER" if item["pile_support_kind"] == "ROW" else "SHELF",
                support_container_id=container_ids[int(support_source)] if support_source is not None else None,
                pile_alignment="RIGHT",
            )
        )
    existing_outside = set(
        session.scalars(select(VisualOutsideArea.area_kind).where(VisualOutsideArea.library_id == library_id))
    )
    for item in records.outside_areas:
        if item["area_kind"] in existing_outside:
            continue
        x, floor, width, height = _world_rect(item)
        session.add(
            VisualOutsideArea(
                library_id=library_id,
                area_kind=str(item["area_kind"]),
                x_mm=x,
                y_mm=floor,
                width_mm=width,
                height_mm=height,
            )
        )

    stored_keys: list[str] = []
    try:
        for item in records.books:
            filename = item["cover_filename"]
            if not filename:
                continue
            processed = process_cover_image((extracted / "covers" / str(filename)).read_bytes(), settings)
            object_key = f"covers/{uuid4().hex}.webp"
            storage.put(object_key, processed.content)
            stored_keys.append(object_key)
            session.add(
                BookCover(
                    library_id=library_id,
                    book_id=book_ids[int(item["source_id"])],
                    object_key=object_key,
                    byte_size=len(processed.content),
                    width_px=processed.width_px,
                    height_px=processed.height_px,
                    sha256=processed.sha256,
                    uploaded_by_user_id=actor_user_id,
                )
            )
        session.add(
            LibraryAuditEvent(
                library_id=library_id,
                actor_user_id=actor_user_id,
                event_type="local_zip_imported",
                details={
                    "source_fingerprint": records.source_fingerprint,
                    "reading_owner_user_id": str(reading_owner_user_id),
                    "counts": {
                        "bookcases": len(records.bookcases),
                        "shelves": len(records.shelves),
                        "containers": len(records.containers),
                        "books": len(records.books),
                        "contributors": len(records.contributors),
                        "readings": len(records.readings),
                        "loans": len(records.loans),
                        "covers": len(stored_keys),
                    },
                },
            )
        )
        session.flush()
    except Exception:
        for key in stored_keys:
            try:
                storage.delete(key)
            except OSError:
                pass
        raise
    counts = {
        "bookcases": len(bookcase_ids),
        "shelves": len(shelf_ids),
        "containers": len(container_ids),
        "books": len(book_ids),
        "contributors": len(records.contributors),
        "readings": len(records.readings),
        "loans": len(records.loans),
        "covers": len(stored_keys),
    }
    expected_persisted = {
        "bookcases": (Bookcase, Bookcase.id, tuple(bookcase_ids.values()), counts["bookcases"]),
        "shelves": (Shelf, Shelf.id, tuple(shelf_ids.values()), counts["shelves"]),
        "containers": (Container, Container.id, tuple(container_ids.values()), counts["containers"]),
        "books": (Book, Book.id, tuple(book_ids.values()), counts["books"]),
        "contributors": (BookContributor, BookContributor.book_id, tuple(book_ids.values()), counts["contributors"]),
        "readings": (ReadingSession, ReadingSession.book_id, tuple(book_ids.values()), counts["readings"]),
        "loans": (Loan, Loan.book_id, tuple(book_ids.values()), counts["loans"]),
        "covers": (BookCover, BookCover.book_id, tuple(book_ids.values()), counts["covers"]),
    }
    try:
        for name, (model, column, identifiers, expected) in expected_persisted.items():
            actual = session.scalar(
                select(func.count()).select_from(model).where(column.in_(identifiers))
            ) if identifiers else 0
            if actual != expected:
                raise LocalImportConflict(
                    f"Post-import verification failed for {name}: expected {expected}, found {actual}."
                )
    except Exception:
        for key in stored_keys:
            try:
                storage.delete(key)
            except OSError:
                pass
        raise
    return counts, stored_keys


def _portable_values(model, source: dict[str, Any], excluded: set[str]) -> dict[str, Any]:
    values: dict[str, Any] = {}
    for column in model.__table__.columns:
        if column.name in excluded or column.computed is not None or column.name not in source:
            continue
        value = source[column.name]
        if value is not None and isinstance(column.type, DateTime):
            value = _datetime(value)
        elif value is not None and isinstance(column.type, Date):
            value = _date(value)
        elif value is not None and isinstance(column.type, Numeric):
            value = _decimal(value)
        values[column.name] = value
    return values


def consolidate_server_v1(
    *,
    session: Session,
    storage: CoverStorage,
    settings: Settings,
    records: CanonicalServerV1Records,
    extracted: Path,
    library_id: UUID,
    member_mapping: dict[str, UUID],
    actor_user_id: UUID,
) -> tuple[dict[str, int], list[str]]:
    """Restore one portable Server library with fresh shared-domain UUIDs."""
    existing_names = {
        name.casefold()
        for name in session.scalars(select(Bookcase.name).where(Bookcase.library_id == library_id))
    }
    conflicts = [str(item["name"]) for item in records.bookcases if str(item["name"]).casefold() in existing_names]
    if conflicts:
        raise LocalImportConflict(
            "Furniture names already exist in the destination: " + ", ".join(conflicts)
        )

    bookcase_ids = {str(item["id"]): uuid4() for item in records.bookcases}
    shelf_ids = {str(item["id"]): uuid4() for item in records.shelves}
    container_ids = {str(item["id"]): uuid4() for item in records.containers}
    book_ids = {str(item["id"]): uuid4() for item in records.books}

    session.add_all([
        Bookcase(
            id=bookcase_ids[str(item["id"])], library_id=library_id,
            **_portable_values(Bookcase, item, {"id", "library_id"}),
        ) for item in records.bookcases
    ])
    session.flush()
    session.add_all([
        Shelf(
            id=shelf_ids[str(item["id"])], library_id=library_id,
            bookcase_id=bookcase_ids[str(item["bookcase_id"])],
            **_portable_values(Shelf, item, {"id", "library_id", "bookcase_id"}),
        ) for item in records.shelves
    ])
    session.flush()
    session.add_all([
        Container(
            id=container_ids[str(item["id"])], library_id=library_id,
            shelf_id=shelf_ids[str(item["shelf_id"])],
            **_portable_values(Container, item, {"id", "library_id", "shelf_id"}),
        ) for item in records.containers
    ])
    session.flush()
    session.add_all([
        Book(
            id=book_ids[str(item["id"])], library_id=library_id,
            container_id=container_ids[str(item["container_id"])] if item.get("container_id") else None,
            **_portable_values(Book, item, {"id", "library_id", "container_id"}),
        ) for item in records.books
    ])
    session.flush()
    session.add_all([
        BookContributor(
            id=uuid4(), library_id=library_id,
            book_id=book_ids[str(item["book_id"])],
            **_portable_values(BookContributor, item, {"id", "library_id", "book_id", "normalized_name"}),
        ) for item in records.contributors
    ])

    mapped_readings = [item for item in records.readings if str(item["user_id"]) in member_mapping]
    mapped_personal = [item for item in records.personal_book_records if str(item["user_id"]) in member_mapping]
    session.add_all([
        ReadingSession(
            id=uuid4(), library_id=library_id,
            book_id=book_ids[str(item["book_id"])],
            user_id=member_mapping[str(item["user_id"])],
            **_portable_values(ReadingSession, item, {"id", "library_id", "book_id", "user_id"}),
        ) for item in mapped_readings
    ])
    session.add_all([
        Loan(
            id=uuid4(), library_id=library_id,
            book_id=book_ids[str(item["book_id"])],
            **_portable_values(Loan, item, {"id", "library_id", "book_id"}),
        ) for item in records.loans
    ])
    session.add_all([
        PersonalBookRecord(
            id=uuid4(), library_id=library_id,
            book_id=book_ids[str(item["book_id"])],
            user_id=member_mapping[str(item["user_id"])],
            **_portable_values(PersonalBookRecord, item, {"id", "library_id", "book_id", "user_id"}),
        ) for item in mapped_personal
    ])
    session.add_all([
        VisualBookcaseLayout(
            library_id=library_id,
            bookcase_id=bookcase_ids[str(item["bookcase_id"])],
            **_portable_values(VisualBookcaseLayout, item, {"library_id", "bookcase_id"}),
        ) for item in records.bookcase_layouts
    ])
    session.add_all([
        VisualShelfLayout(
            library_id=library_id,
            shelf_id=shelf_ids[str(item["shelf_id"])],
            **_portable_values(VisualShelfLayout, item, {"library_id", "shelf_id"}),
        ) for item in records.shelf_layouts
    ])
    session.add_all([
        VisualContainerLayout(
            library_id=library_id,
            container_id=container_ids[str(item["container_id"])],
            support_container_id=(container_ids[str(item["support_container_id"])] if item.get("support_container_id") else None),
            **_portable_values(VisualContainerLayout, item, {"library_id", "container_id", "support_container_id"}),
        ) for item in records.container_layouts
    ])
    existing_outside = set(session.scalars(
        select(VisualOutsideArea.area_kind).where(VisualOutsideArea.library_id == library_id)
    ))
    imported_outside = [item for item in records.outside_areas if item["area_kind"] not in existing_outside]
    session.add_all([
        VisualOutsideArea(
            library_id=library_id,
            **_portable_values(VisualOutsideArea, item, {"library_id"}),
        ) for item in imported_outside
    ])

    stored_keys: list[str] = []
    try:
        for item in records.covers:
            processed = process_cover_image((extracted / str(item["archive_name"])).read_bytes(), settings)
            object_key = f"covers/{uuid4().hex}.webp"
            storage.put(object_key, processed.content)
            stored_keys.append(object_key)
            uploader = item.get("uploaded_by_member_key")
            session.add(BookCover(
                id=uuid4(), library_id=library_id,
                book_id=book_ids[str(item["book_id"])],
                object_key=object_key, byte_size=len(processed.content),
                width_px=processed.width_px, height_px=processed.height_px,
                sha256=processed.sha256,
                uploaded_by_user_id=member_mapping.get(str(uploader)) if uploader else None,
                created_at=_datetime(item["created_at"]), updated_at=_datetime(item["updated_at"]),
            ))
        counts = {
            "bookcases": len(records.bookcases), "shelves": len(records.shelves),
            "containers": len(records.containers), "books": len(records.books),
            "contributors": len(records.contributors), "readings": len(mapped_readings),
            "loans": len(records.loans), "personal_book_records": len(mapped_personal),
            "covers": len(stored_keys), "outside_areas": len(imported_outside),
            "omitted_readings": len(records.readings) - len(mapped_readings),
            "omitted_personal_book_records": len(records.personal_book_records) - len(mapped_personal),
        }
        session.add(LibraryAuditEvent(
            library_id=library_id, actor_user_id=actor_user_id,
            event_type="server_zip_restored",
            details={
                "source_fingerprint": records.source_fingerprint,
                "mapped_member_count": len(member_mapping), "counts": counts,
            },
        ))
        session.flush()
        checks = (
            (Bookcase, Bookcase.id, tuple(bookcase_ids.values()), counts["bookcases"]),
            (Shelf, Shelf.id, tuple(shelf_ids.values()), counts["shelves"]),
            (Container, Container.id, tuple(container_ids.values()), counts["containers"]),
            (Book, Book.id, tuple(book_ids.values()), counts["books"]),
            (ReadingSession, ReadingSession.book_id, tuple(book_ids.values()), counts["readings"]),
            (Loan, Loan.book_id, tuple(book_ids.values()), counts["loans"]),
            (BookCover, BookCover.book_id, tuple(book_ids.values()), counts["covers"]),
        )
        for model, column, identifiers, expected in checks:
            actual = session.scalar(select(func.count()).select_from(model).where(column.in_(identifiers))) if identifiers else 0
            if actual != expected:
                raise LocalImportConflict(
                    f"Post-restore verification failed: expected {expected}, found {actual}."
                )
    except Exception:
        for key in stored_keys:
            try:
                storage.delete(key)
            except OSError:
                pass
        raise
    return counts, stored_keys
