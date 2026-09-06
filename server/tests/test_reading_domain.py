from datetime import date

import pytest

from bookpile_server.services.reading_domain import (
    ReadingPeriod,
    ReadingRuleViolation,
    ReadingState,
    SessionState,
    derive_reading_state,
    format_active_reading_count,
    inclusive_reading_days,
    reading_rate_pages_per_day,
    validate_history,
    validate_period,
)


def completed(start: date, finish: date, order: int = 0) -> ReadingPeriod:
    return ReadingPeriod(SessionState.COMPLETED, start, finish, creation_order=order)


def test_session_shapes_require_complete_known_or_fully_unknown_dates() -> None:
    validate_period(ReadingPeriod(SessionState.ACTIVE, date(2026, 1, 1)))
    validate_period(completed(date(2026, 1, 1), date(2026, 1, 1)))
    validate_period(
        ReadingPeriod(SessionState.COMPLETED, dates_unknown=True)
    )

    invalid = [
        ReadingPeriod(SessionState.ACTIVE),
        ReadingPeriod(SessionState.ACTIVE, date(2026, 1, 1), date(2026, 1, 2)),
        ReadingPeriod(SessionState.COMPLETED, date(2026, 1, 1)),
        ReadingPeriod(SessionState.COMPLETED, finished_date=date(2026, 1, 2)),
        ReadingPeriod(
            SessionState.COMPLETED,
            date(2026, 1, 1),
            date(2026, 1, 2),
            dates_unknown=True,
        ),
        completed(date(2026, 1, 2), date(2026, 1, 1)),
    ]
    for period in invalid:
        with pytest.raises(ReadingRuleViolation):
            validate_period(period)


def test_history_allows_shared_boundary_but_rejects_overlap_and_duplicates() -> None:
    assert len(
        validate_history(
            [
                completed(date(2026, 3, 10), date(2026, 3, 15)),
                completed(date(2026, 3, 15), date(2026, 3, 15)),
                completed(date(2026, 3, 15), date(2026, 3, 16)),
            ]
        )
    ) == 3

    with pytest.raises(ReadingRuleViolation, match="overlap"):
        validate_history(
            [
                completed(date(2026, 3, 10), date(2026, 3, 16)),
                completed(date(2026, 3, 15), date(2026, 3, 17)),
            ]
        )
    with pytest.raises(ReadingRuleViolation, match="indistinguishable"):
        validate_history(
            [
                completed(date(2026, 3, 15), date(2026, 3, 15)),
                completed(date(2026, 3, 15), date(2026, 3, 15)),
            ]
        )


def test_unknown_history_is_unique_and_always_sorted_first() -> None:
    unknown = ReadingPeriod(
        SessionState.COMPLETED, dates_unknown=True, creation_order=2
    )
    known = completed(date(2020, 1, 1), date(2020, 1, 2), 1)
    assert validate_history([known, unknown]) == (unknown, known)
    with pytest.raises(ReadingRuleViolation, match="Only one unknown"):
        validate_history([unknown, ReadingPeriod(SessionState.COMPLETED, dates_unknown=True)])


def test_personal_state_is_derived_from_sessions() -> None:
    first = completed(date(2026, 1, 1), date(2026, 1, 3))
    assert derive_reading_state([]) == ReadingState.PENDING
    assert derive_reading_state([ReadingPeriod(SessionState.ACTIVE, date(2026, 1, 1))]) == ReadingState.READING
    assert derive_reading_state([first]) == ReadingState.READ
    assert derive_reading_state([first, ReadingPeriod(SessionState.ACTIVE, date(2026, 1, 3))]) == ReadingState.REREADING


def test_duration_rate_and_active_count_use_agreed_display_rules() -> None:
    same_day = completed(date(2026, 4, 2), date(2026, 4, 2))
    assert inclusive_reading_days(same_day) == 1
    assert reading_rate_pages_per_day(240, same_day) == 240
    assert reading_rate_pages_per_day(None, same_day) is None
    assert format_active_reading_count(2, 0) == "2"
    assert format_active_reading_count(0, 2) == "+2"
    assert format_active_reading_count(1, 1) == "1+1"
