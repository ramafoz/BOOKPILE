from datetime import date
from uuid import UUID

from fastapi import APIRouter, HTTPException, Response, status

from ...schemas import (
    ActiveLoanWrite,
    HistoricalLoanWrite,
    OwnerBookLoansResponse,
    OwnerLoanResponse,
    OwnerLoanOverviewResponse,
    ReturnLoanWrite,
    ViewerBookLoansResponse,
    ViewerLoanResponse,
    ViewerLoanOverviewResponse,
)
from ...services.loans import (
    LoanAccessError,
    LoanConflictError,
    LoanNotFoundError,
    LoanValidationError,
)
from ..dependencies import (
    CsrfDependency,
    CurrentAuthDependency,
    LoanServiceDependency,
)


router = APIRouter(
    prefix="/libraries/{library_id}/catalogue/{book_id}/loans",
    tags=["shared loans"],
)
overview_router = APIRouter(
    prefix="/libraries/{library_id}/loan-overview",
    tags=["shared loans"],
)


def loan_error(exc: Exception) -> HTTPException:
    if isinstance(exc, LoanNotFoundError):
        return HTTPException(status_code=404, detail="Loan record not found")
    if isinstance(exc, LoanAccessError):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, LoanValidationError):
        return HTTPException(status_code=422, detail=str(exc))
    if isinstance(exc, LoanConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    raise exc


def viewer_response(item) -> ViewerLoanResponse:
    return ViewerLoanResponse(**item.__dict__)


def owner_response(item) -> OwnerLoanResponse:
    return OwnerLoanResponse(**item.__dict__)


def record_response(item) -> OwnerLoanResponse:
    return OwnerLoanResponse(
        id=item.id,
        state=item.state,
        loaned_to=item.loaned_to,
        notes=item.notes,
        loaned_date=item.loaned_date,
        expected_return_date=item.expected_return_date,
        returned_date=item.returned_date,
        created_at=item.created_at,
        updated_at=item.updated_at,
        overdue=(
            item.state == "ACTIVE"
            and item.expected_return_date is not None
            and item.expected_return_date < date.today()
        ),
    )


@overview_router.get(
    "", response_model=OwnerLoanOverviewResponse | ViewerLoanOverviewResponse
)
def get_loan_overview(
    library_id: UUID,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
) -> OwnerLoanOverviewResponse | ViewerLoanOverviewResponse:
    try:
        result = service.catalogue_overview(
            library_id=library_id, actor_user_id=context.user_id
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    if result.owner_items is not None:
        return OwnerLoanOverviewResponse(
            library_id=library_id,
            total_active=result.total_active,
            total_overdue=result.total_overdue,
            loans=[owner_response(item) for item in result.owner_items],
        )
    items = result.viewer_items or []
    return ViewerLoanOverviewResponse(
        library_id=library_id,
        total_active=result.total_active,
        total_overdue=result.total_overdue,
        loans=[viewer_response(item) for item in items],
    )


@router.get("", response_model=OwnerBookLoansResponse | ViewerBookLoansResponse)
def get_book_loans(
    library_id: UUID,
    book_id: UUID,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
) -> OwnerBookLoansResponse | ViewerBookLoansResponse:
    try:
        result = service.projection(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    if result.owner_items is not None:
        return OwnerBookLoansResponse(
            library_id=library_id,
            book_id=book_id,
            total_loans=len(result.owner_items),
            loans=[owner_response(item) for item in result.owner_items],
        )
    items = result.viewer_items or []
    return ViewerBookLoansResponse(
        library_id=library_id,
        book_id=book_id,
        total_loans=len(items),
        loans=[viewer_response(item) for item in items],
    )


@router.post("/active", response_model=OwnerLoanResponse, status_code=201)
def start_loan(
    library_id: UUID,
    book_id: UUID,
    payload: ActiveLoanWrite,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> OwnerLoanResponse:
    try:
        record = service.start(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            **payload.model_dump(),
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    return record_response(record)


@router.post("/active/return", response_model=OwnerLoanResponse)
def return_loan(
    library_id: UUID,
    book_id: UUID,
    payload: ReturnLoanWrite,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> OwnerLoanResponse:
    try:
        record = service.return_active(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            returned_date=payload.returned_date,
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    return record_response(record)


@router.delete("/active", status_code=status.HTTP_204_NO_CONTENT)
def cancel_loan(
    library_id: UUID,
    book_id: UUID,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        service.cancel_active(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    return Response(status_code=204)


@router.post("/history", response_model=OwnerLoanResponse, status_code=201)
def add_historical_loan(
    library_id: UUID,
    book_id: UUID,
    payload: HistoricalLoanWrite,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> OwnerLoanResponse:
    try:
        record = service.add_historical(
            library_id=library_id,
            book_id=book_id,
            actor_user_id=context.user_id,
            **payload.model_dump(),
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    return record_response(record)


@router.put("/{loan_id}", response_model=OwnerLoanResponse)
def edit_historical_loan(
    library_id: UUID,
    book_id: UUID,
    loan_id: UUID,
    payload: HistoricalLoanWrite,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> OwnerLoanResponse:
    try:
        record = service.edit_historical(
            library_id=library_id,
            book_id=book_id,
            loan_id=loan_id,
            actor_user_id=context.user_id,
            **payload.model_dump(),
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    return record_response(record)


@router.delete("/{loan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_historical_loan(
    library_id: UUID,
    book_id: UUID,
    loan_id: UUID,
    service: LoanServiceDependency,
    context: CurrentAuthDependency,
    _csrf: CsrfDependency,
) -> Response:
    try:
        service.delete_historical(
            library_id=library_id,
            book_id=book_id,
            loan_id=loan_id,
            actor_user_id=context.user_id,
        )
    except Exception as exc:
        raise loan_error(exc) from exc
    return Response(status_code=204)
