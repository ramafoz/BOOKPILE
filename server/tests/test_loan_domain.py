from datetime import date

import pytest

from bookpile_server.services.loan_domain import (
    CustodyState,
    LoanPeriod,
    LoanRuleViolation,
    LoanState,
    derive_custody_state,
    is_overdue,
    normalize_loaned_to,
    normalize_notes,
    order_loan_history,
    validate_loan,
)


TODAY = date(2026, 9, 8)


def test_text_is_trimmed_limited_and_empty_notes_become_none() -> None:
    assert normalize_loaned_to("  Alice  ") == "Alice"
    assert normalize_notes("  private  ") == "private"
    assert normalize_notes("  ") is None
    with pytest.raises(LoanRuleViolation, match="required"):
        normalize_loaned_to("   ")
    with pytest.raises(LoanRuleViolation, match="300"):
        normalize_loaned_to("a" * 301)
    with pytest.raises(LoanRuleViolation, match="4000"):
        normalize_notes("n" * 4001)


def test_active_and_historical_loan_date_rules() -> None:
    validate_loan(LoanPeriod(LoanState.ACTIVE, "Alice"), today=TODAY)
    validate_loan(
        LoanPeriod(LoanState.RETURNED, "Alice", returned_date=None),
        today=TODAY,
    )
    invalid = [
        LoanPeriod(LoanState.ACTIVE, "Alice", returned_date=TODAY),
        LoanPeriod(LoanState.ACTIVE, "Alice", loaned_date=date(2026, 9, 9)),
        LoanPeriod(LoanState.RETURNED, "Alice", returned_date=date(2026, 9, 9)),
        LoanPeriod(
            LoanState.ACTIVE,
            "Alice",
            loaned_date=date(2026, 9, 2),
            expected_return_date=date(2026, 9, 1),
        ),
        LoanPeriod(
            LoanState.RETURNED,
            "Alice",
            loaned_date=date(2026, 9, 2),
            returned_date=date(2026, 9, 1),
        ),
    ]
    for loan in invalid:
        with pytest.raises(LoanRuleViolation):
            validate_loan(loan, today=TODAY)


def test_unknown_histories_sort_before_dated_histories() -> None:
    unknown = LoanPeriod(LoanState.RETURNED, "Alice", creation_order=2)
    dated = LoanPeriod(
        LoanState.RETURNED,
        "Bob",
        loaned_date=date(2020, 1, 1),
        returned_date=date(2020, 1, 2),
        creation_order=1,
    )
    assert order_loan_history([dated, unknown]) == (unknown, dated)


def test_overdue_and_custody_precedence() -> None:
    active = LoanPeriod(
        LoanState.ACTIVE,
        "Alice",
        loaned_date=date(2026, 9, 1),
        expected_return_date=date(2026, 9, 7),
    )
    assert is_overdue(active, today=TODAY)
    assert derive_custody_state(
        has_active_loan=True, has_active_reading=True
    ) == CustodyState.ON_LOAN
    assert derive_custody_state(
        has_active_loan=False, has_active_reading=True
    ) == CustodyState.BEING_READ
    assert derive_custody_state(
        has_active_loan=False, has_active_reading=False
    ) == CustodyState.SHELVED
