"""Pure Phase 5 reading rules, independent from persistence and HTTP."""
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Iterable


class ReadingState(StrEnum):
    PENDING = "PENDING"
    READING = "READING"
    REREADING = "REREADING"
    READ = "READ"


class SessionState(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"


class ReadingRuleViolation(ValueError):
    """A proposed personal reading history violates a canonical rule."""


@dataclass(frozen=True, slots=True)
class ReadingPeriod:
    state: SessionState
    started_date: date | None = None
    finished_date: date | None = None
    dates_unknown: bool = False
    creation_order: int = 0


def validate_period(period: ReadingPeriod) -> None:
    if period.state == SessionState.ACTIVE:
        if (
            period.dates_unknown
            or period.started_date is None
            or period.finished_date is not None
        ):
            raise ReadingRuleViolation(
                "An active reading needs a known start and no finish date."
            )
        return

    if period.state != SessionState.COMPLETED:
        raise ReadingRuleViolation("Unknown reading-session state.")
    if period.dates_unknown:
        if period.started_date is not None or period.finished_date is not None:
            raise ReadingRuleViolation(
                "An unknown historical reading cannot contain either date."
            )
        return
    if period.started_date is None or period.finished_date is None:
        raise ReadingRuleViolation(
            "A known completed reading needs both start and finish dates."
        )
    if period.finished_date < period.started_date:
        raise ReadingRuleViolation("A reading cannot finish before it starts.")


def validate_history(periods: Iterable[ReadingPeriod]) -> tuple[ReadingPeriod, ...]:
    history = tuple(periods)
    for period in history:
        validate_period(period)

    if sum(period.state == SessionState.ACTIVE for period in history) > 1:
        raise ReadingRuleViolation("Only one active reading is allowed.")
    if sum(period.dates_unknown for period in history) > 1:
        raise ReadingRuleViolation(
            "Only one unknown historical reading is allowed."
        )

    known = sorted(
        (period for period in history if not period.dates_unknown),
        key=lambda period: (
            period.started_date or date.min,
            period.finished_date or date.max,
            period.creation_order,
        ),
    )
    for previous, current in zip(known, known[1:], strict=False):
        assert previous.started_date is not None
        assert current.started_date is not None
        previous_end = previous.finished_date or date.max
        current_end = current.finished_date or date.max
        if (
            previous.started_date == current.started_date
            and previous_end == current_end
        ):
            raise ReadingRuleViolation(
                "Two readings cannot have indistinguishable dates."
            )
        # A boundary day may be shared: one session can finish on the day the
        # next starts. Any stricter intersection is an overlap.
        if current.started_date < previous_end:
            raise ReadingRuleViolation("Reading sessions cannot overlap.")

    return order_history(history)


def order_history(periods: Iterable[ReadingPeriod]) -> tuple[ReadingPeriod, ...]:
    return tuple(
        sorted(
            periods,
            key=lambda period: (
                0 if period.dates_unknown else 1,
                period.started_date or date.min,
                period.finished_date or date.max,
                period.creation_order,
            ),
        )
    )


def derive_reading_state(periods: Iterable[ReadingPeriod]) -> ReadingState:
    history = validate_history(periods)
    active = next(
        (period for period in history if period.state == SessionState.ACTIVE),
        None,
    )
    completed_count = sum(
        period.state == SessionState.COMPLETED for period in history
    )
    if active is not None:
        return ReadingState.REREADING if completed_count else ReadingState.READING
    return ReadingState.READ if completed_count else ReadingState.PENDING


def inclusive_reading_days(period: ReadingPeriod) -> int | None:
    validate_period(period)
    if period.state != SessionState.COMPLETED or period.dates_unknown:
        return None
    assert period.started_date is not None
    assert period.finished_date is not None
    return (period.finished_date - period.started_date).days + 1


def reading_rate_pages_per_day(
    page_count: int | None, period: ReadingPeriod
) -> float | None:
    if page_count is None or page_count <= 0:
        return None
    days = inclusive_reading_days(period)
    return None if days is None else page_count / days


def format_active_reading_count(initial_readings: int, rereadings: int) -> str:
    if initial_readings < 0 or rereadings < 0:
        raise ReadingRuleViolation("Reading counts cannot be negative.")
    if rereadings == 0:
        return str(initial_readings)
    if initial_readings == 0:
        return f"+{rereadings}"
    return f"{initial_readings}+{rereadings}"
