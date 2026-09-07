from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Response, status

from ...schemas import (
    BookReadingResponse,
    FinishReadingRequest,
    GoodreadsReviewResponse,
    GoodreadsWrite,
    HistoricalReadingWrite,
    ReadingSessionResponse,
    ReadingCatalogueItemResponse,
    ReadingCatalogueOverviewResponse,
    StartReadingRequest,
)
from ...services.readings import (
    ReadingAccessError,
    ReadingConflictError,
    ReadingNotFoundError,
    ReadingValidationError,
)
from ...services.reading_domain import format_active_reading_count
from ...services.library_access import LibraryNotFoundError
from ..dependencies import (
    CsrfDependency,
    CurrentAuthDependency,
    LibraryAccessServiceDependency,
    ReadingServiceDependency,
)


router = APIRouter(
    prefix="/libraries/{library_id}/catalogue/{book_id}/reading",
    tags=["personal readings"],
)
overview_router = APIRouter(prefix="/libraries/{library_id}/reading-overview", tags=["personal readings"])


@overview_router.get("", response_model=ReadingCatalogueOverviewResponse)
def get_reading_catalogue_overview(
    library_id: UUID,
    service: ReadingServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    perspective_user_id: UUID | None = Query(default=None),
) -> ReadingCatalogueOverviewResponse:
    try:
        access = access_service.require_catalogue(
            library_id=library_id, user_id=context.user_id
        )
        target = perspective_user_id or access.selected_reading_user_id or context.user_id
        overview = service.catalogue_overview(
            library_id=library_id,
            actor_user_id=context.user_id,
            perspective_user_id=target,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return ReadingCatalogueOverviewResponse(
        perspective_user_id=overview.user_id,
        writable=overview.writable,
        pending=overview.pending,
        reading=overview.reading,
        rereading=overview.rereading,
        read=overview.read,
        active_display=format_active_reading_count(overview.reading, overview.rereading),
        items=[ReadingCatalogueItemResponse(
            book_id=item.book_id,
            state=item.state.value,
            active_reader_present=item.active_reader_present,
            goodreads_url=item.goodreads_url,
        ) for item in overview.items],
    )


def reading_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (ReadingNotFoundError, LibraryNotFoundError)):
        return HTTPException(status_code=404, detail="Reading record not found")
    if isinstance(exc, ReadingAccessError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, ReadingValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, ReadingConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def session_response(item) -> ReadingSessionResponse:
    return ReadingSessionResponse(
        id=item.id,
        state=item.state,
        started_date=item.started_date,
        finished_date=item.finished_date,
        dates_unknown=item.dates_unknown,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.get("", response_model=BookReadingResponse)
def get_book_reading(
    library_id: UUID,
    book_id: UUID,
    service: ReadingServiceDependency,
    access_service: LibraryAccessServiceDependency,
    context: CurrentAuthDependency,
    perspective_user_id: UUID | None = Query(default=None),
    limit: int = Query(default=100, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> BookReadingResponse:
    try:
        access = access_service.require_catalogue(
            library_id=library_id, user_id=context.user_id
        )
        target = (
            perspective_user_id
            or access.selected_reading_user_id
            or context.user_id
        )
        projection = service.projection(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            perspective_user_id=target,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return BookReadingResponse(
        library_id=library_id,
        book_id=book_id,
        perspective_user_id=projection.user_id,
        state=projection.state.value,
        active_reader_present=projection.active_reader_present,
        writable=projection.writable,
        total_sessions=len(projection.sessions),
        limit=limit,
        offset=offset,
        sessions=[
            session_response(item)
            for item in projection.sessions[offset : offset + limit]
        ],
    )


@router.post("/sessions/start", response_model=ReadingSessionResponse, status_code=201)
def start_reading(
    library_id: UUID,
    book_id: UUID,
    payload: StartReadingRequest,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> ReadingSessionResponse:
    try:
        item = service.start(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            started=payload.started_date,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return session_response(item)


@router.post("/sessions/{session_id}/finish", response_model=ReadingSessionResponse)
def finish_reading(
    library_id: UUID,
    book_id: UUID,
    session_id: UUID,
    payload: FinishReadingRequest,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> ReadingSessionResponse:
    try:
        item = service.finish(
            library_id=library_id,
            book_id=book_id,
            session_id=session_id,
            actor_user_id=context.user_id,
            finished=payload.finished_date,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return session_response(item)


@router.delete("/sessions/{session_id}/cancel", status_code=204)
def cancel_reading(
    library_id: UUID,
    book_id: UUID,
    session_id: UUID,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        service.cancel(
            library_id=library_id,
            book_id=book_id,
            session_id=session_id,
            actor_user_id=context.user_id,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return Response(status_code=204)


@router.post("/sessions/historical", response_model=ReadingSessionResponse, status_code=201)
def add_historical_reading(
    library_id: UUID,
    book_id: UUID,
    payload: HistoricalReadingWrite,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> ReadingSessionResponse:
    try:
        item = service.add_historical(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            started=payload.started_date,
            finished=payload.finished_date,
            dates_unknown=payload.dates_unknown,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return session_response(item)


@router.put("/sessions/{session_id}", response_model=ReadingSessionResponse)
def edit_historical_reading(
    library_id: UUID,
    book_id: UUID,
    session_id: UUID,
    payload: HistoricalReadingWrite,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> ReadingSessionResponse:
    try:
        item = service.edit_completed(
            library_id=library_id,
            book_id=book_id,
            session_id=session_id,
            actor_user_id=context.user_id,
            started=payload.started_date,
            finished=payload.finished_date,
            dates_unknown=payload.dates_unknown,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return session_response(item)


@router.delete("/sessions/{session_id}", status_code=204)
def delete_historical_reading(
    library_id: UUID,
    book_id: UUID,
    session_id: UUID,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        service.delete_completed(
            library_id=library_id,
            book_id=book_id,
            session_id=session_id,
            actor_user_id=context.user_id,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return Response(status_code=204)


@router.get("/goodreads", response_model=list[GoodreadsReviewResponse])
def get_goodreads_reviews(
    library_id: UUID,
    book_id: UUID,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
) -> list[GoodreadsReviewResponse]:
    try:
        records = service.reviews(
            library_id=library_id, book_id=book_id, actor_user_id=context.user_id
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    return [
        GoodreadsReviewResponse(user_id=record.user_id, username=username, url=record.goodreads_url)
        for record, username in records
        if record.goodreads_url is not None
    ]


@router.put("/goodreads/me", response_model=GoodreadsReviewResponse | None)
def set_my_goodreads_review(
    library_id: UUID,
    book_id: UUID,
    payload: GoodreadsWrite,
    service: ReadingServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> GoodreadsReviewResponse | None:
    try:
        record = service.set_goodreads(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            url=payload.url,
        )
    except Exception as exc:
        raise reading_error(exc) from exc
    if record is None:
        return None
    return GoodreadsReviewResponse(
        user_id=context.user_id,
        username=service.username(context.user_id),
        url=record.goodreads_url or "",
    )
