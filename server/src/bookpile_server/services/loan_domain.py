"""Pure rules for shared physical-copy loans."""
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Iterable


class LoanState(StrEnum):
    ACTIVE = "ACTIVE"
    RETURNED = "RETURNED"


class CustodyState(StrEnum):
    ON_LOAN = "ON_LOAN"
    BEING_READ = "BEING_READ"
    SHELVED = "SHELVED"


class LoanRuleViolation(ValueError):
    """A proposed loan violates a canonical rule."""


@dataclass(frozen=True, slots=True)
class LoanPeriod:
    state: LoanState
    loaned_to: str
    loaned_date: date | None = None
    expected_return_date: date | None = None
    returned_date: date | None = None
    notes: str | None = None
    creation_order: int = 0


def normalize_loaned_to(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise LoanRuleViolation("The borrower is required.")
    if len(normalized) > 300:
        raise LoanRuleViolation("The borrower cannot exceed 300 characters.")
    return normalized


def normalize_notes(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    if len(normalized) > 4000:
        raise LoanRuleViolation("Loan notes cannot exceed 4000 characters.")
    return normalized or None


def validate_loan(period: LoanPeriod, *, today: date | None = None) -> None:
    normalize_loaned_to(period.loaned_to)
    normalize_notes(period.notes)
    if period.state == LoanState.ACTIVE and period.returned_date is not None:
        raise LoanRuleViolation("An active loan cannot have a return date.")
    if period.state not in (LoanState.ACTIVE, LoanState.RETURNED):
        raise LoanRuleViolation("Unknown loan state.")
    if (
        period.loaned_date is not None
        and period.expected_return_date is not None
        and period.expected_return_date < period.loaned_date
    ):
        raise LoanRuleViolation("Expected return cannot precede the loan date.")
    if (
        period.loaned_date is not None
        and period.returned_date is not None
        and period.returned_date < period.loaned_date
    ):
        raise LoanRuleViolation("Return cannot precede the loan date.")
    reference = today or date.today()
    if period.loaned_date is not None and period.loaned_date > reference:
        raise LoanRuleViolation("The loan date cannot be in the future.")
    if period.returned_date is not None and period.returned_date > reference:
        raise LoanRuleViolation("The return date cannot be in the future.")


def order_loan_history(periods: Iterable[LoanPeriod]) -> tuple[LoanPeriod, ...]:
    history = tuple(periods)
    for period in history:
        validate_loan(period)
    return tuple(
        sorted(
            history,
            key=lambda period: (
                0 if period.loaned_date is None else 1,
                period.loaned_date or date.min,
                period.returned_date or date.max,
                period.creation_order,
            ),
        )
    )


def is_overdue(period: LoanPeriod, *, today: date | None = None) -> bool:
    validate_loan(period, today=today)
    return (
        period.state == LoanState.ACTIVE
        and period.expected_return_date is not None
        and period.expected_return_date < (today or date.today())
    )


def derive_custody_state(
    *, has_active_loan: bool, has_active_reading: bool
) -> CustodyState:
    if has_active_loan:
        return CustodyState.ON_LOAN
    if has_active_reading:
        return CustodyState.BEING_READ
    return CustodyState.SHELVED
