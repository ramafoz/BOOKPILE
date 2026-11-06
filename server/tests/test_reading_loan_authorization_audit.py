from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from bookpile_server.models import (
    LibraryAuditEvent,
    LibraryMembership,
    Loan,
    PersonalBookRecord,
    ReadingSession,
)
from test_readings_api import (
    authenticate,
    headers,
    reading_url,
    shared_fixture,
    user,
)


def _authenticate(client: TestClient, session: Session, actor) -> None:
    client.cookies.clear()
    authenticate(client, session, actor)


def _snapshot(session: Session) -> dict[str, tuple[tuple[Any, ...], ...]]:
    session.expire_all()

    def rows(model: type[Any], *columns: Any) -> tuple[tuple[Any, ...], ...]:
        values = session.execute(select(*columns).select_from(model)).all()
        return tuple(sorted((tuple(value) for value in values), key=repr))

    return {
        "perspectives": rows(
            LibraryMembership,
            LibraryMembership.id,
            LibraryMembership.user_id,
            LibraryMembership.selected_reading_user_id,
        ),
        "readings": rows(
            ReadingSession,
            ReadingSession.id,
            ReadingSession.library_id,
            ReadingSession.book_id,
            ReadingSession.user_id,
            ReadingSession.state,
            ReadingSession.started_date,
            ReadingSession.finished_date,
            ReadingSession.dates_unknown,
        ),
        "personal_records": rows(
            PersonalBookRecord,
            PersonalBookRecord.id,
            PersonalBookRecord.library_id,
            PersonalBookRecord.book_id,
            PersonalBookRecord.user_id,
            PersonalBookRecord.goodreads_url,
        ),
        "loans": rows(
            Loan,
            Loan.id,
            Loan.library_id,
            Loan.book_id,
            Loan.state,
            Loan.loaned_to,
            Loan.notes,
            Loan.loaned_date,
            Loan.expected_return_date,
            Loan.returned_date,
        ),
        "audit": rows(
            LibraryAuditEvent,
            LibraryAuditEvent.id,
            LibraryAuditEvent.library_id,
            LibraryAuditEvent.actor_user_id,
            LibraryAuditEvent.event_type,
            LibraryAuditEvent.details,
        ),
    }


def _assert_no_private_loan_text(payload: str) -> None:
    assert "A3 Secret Borrower" not in payload
    assert "A3 private address and phone" not in payload
    assert "loaned_to" not in payload
    assert '"notes"' not in payload


def test_reading_perspectives_shared_custody_statistics_and_private_loans(
    client: TestClient,
    session: Session,
) -> None:
    library, book, first, second, catalogue_viewer, _ = shared_fixture(session)
    map_viewer = user(session, "a3_map_viewer")
    session.add(
        LibraryMembership(
            library_id=library.id,
            user_id=map_viewer.id,
            role="VIEWER",
            viewer_scope="CATALOG_AND_MAP",
            selected_reading_user_id=first.id,
        )
    )
    session.commit()
    reading = reading_url(library, book)
    loans = f"/api/v1/libraries/{library.id}/catalogue/{book.id}/loans"
    perspectives = f"/api/v1/libraries/{library.id}/reading-perspectives"
    selected_perspective = f"/api/v1/libraries/{library.id}/reading-perspective"
    reading_overview = f"/api/v1/libraries/{library.id}/reading-overview"
    loan_overview = f"/api/v1/libraries/{library.id}/loan-overview"

    _authenticate(client, session, first)
    started = client.post(
        f"{reading}/sessions/start",
        json={"started_date": "2026-11-01"},
        headers=headers(),
    )
    assert started.status_code == 201, started.text
    active_session_id = started.json()["id"]
    review = client.put(
        f"{reading}/goodreads/me",
        json={"url": "https://www.goodreads.com/review/show/3001"},
        headers=headers(),
    )
    assert review.status_code == 200, review.text

    _authenticate(client, session, second)
    own_projection = client.get(reading)
    first_projection = client.get(
        reading,
        params={"perspective_user_id": first.id},
    )
    assert own_projection.status_code == 200
    assert own_projection.json()["state"] == "PENDING"
    assert own_projection.json()["active_reader_present"] is True
    assert first_projection.status_code == 200
    assert first_projection.json()["state"] == "READING"
    assert first_projection.json()["writable"] is False
    before_cross_owner = _snapshot(session)
    assert client.post(
        f"{reading}/sessions/{active_session_id}/finish",
        json={"finished_date": "2026-11-03"},
        headers=headers(),
    ).status_code == 404
    assert _snapshot(session) == before_cross_owner
    assert client.post(
        f"{reading}/sessions/start",
        json={"started_date": "2026-11-02"},
        headers=headers(),
    ).status_code == 409
    assert _snapshot(session) == before_cross_owner

    _authenticate(client, session, first)
    finished = client.post(
        f"{reading}/sessions/{active_session_id}/finish",
        json={"finished_date": "2026-11-03"},
        headers=headers(),
    )
    assert finished.status_code == 200, finished.text
    historical = client.post(
        f"{reading}/sessions/historical",
        json={
            "started_date": "2026-01-10",
            "finished_date": "2026-01-12",
        },
        headers=headers(),
    )
    assert historical.status_code == 201, historical.text
    statistics = client.get(
        f"{reading_overview}/statistics",
        params={"perspective_user_id": first.id, "reading_year": 2026},
    )
    assert statistics.status_code == 200, statistics.text
    assert statistics.json()["completed_readings"] == 2
    assert statistics.json()["unique_books_read"] == 1

    loan = client.post(
        f"{loans}/active",
        json={
            "loaned_to": "A3 Secret Borrower",
            "notes": "A3 private address and phone",
            "loaned_date": "2026-11-04",
            "expected_return_date": "2026-11-20",
        },
        headers=headers(),
    )
    assert loan.status_code == 201, loan.text
    assert loan.json()["loaned_to"] == "A3 Secret Borrower"
    assert loan.json()["notes"] == "A3 private address and phone"

    _authenticate(client, session, second)
    owner_loan_view = client.get(loans)
    assert owner_loan_view.status_code == 200
    assert owner_loan_view.json()["access"] == "OWNER"
    assert owner_loan_view.json()["loans"][0]["loaned_to"] == "A3 Secret Borrower"
    assert owner_loan_view.json()["loans"][0]["notes"] == "A3 private address and phone"

    for viewer in (catalogue_viewer, map_viewer):
        _authenticate(client, session, viewer)
        available = client.get(perspectives)
        assert available.status_code == 200
        assert {item["user_id"] for item in available.json()} == {
            str(first.id),
            str(second.id),
        }
        assert not any(item["writable"] for item in available.json())

        selected = client.put(
            selected_perspective,
            json={"user_id": str(first.id)},
            headers=headers(),
        )
        assert selected.status_code == 200, selected.text
        assert next(item for item in selected.json() if item["selected"])[
            "user_id"
        ] == str(first.id)

        reading_view = client.get(reading)
        overview = client.get(reading_overview)
        viewer_statistics = client.get(
            f"{reading_overview}/statistics",
            params={"reading_year": 2026},
        )
        reviews = client.get(f"{reading}/goodreads")
        assert reading_view.status_code == 200
        assert reading_view.json()["state"] == "READ"
        assert reading_view.json()["writable"] is False
        assert overview.status_code == 200
        assert overview.json()["read"] == 1
        assert viewer_statistics.status_code == 200
        assert viewer_statistics.json()["completed_readings"] == 2
        assert reviews.status_code == 200
        assert reviews.json() == [
            {
                "user_id": str(first.id),
                "username": first.username,
                "url": "https://www.goodreads.com/review/show/3001",
            }
        ]

        viewer_loans = client.get(loans)
        viewer_loan_overview = client.get(loan_overview)
        viewer_loan_statistics = client.get(f"{loan_overview}/statistics")
        assert viewer_loans.status_code == 200
        assert viewer_loans.json()["access"] == "VIEWER"
        assert viewer_loan_overview.status_code == 200
        assert viewer_loan_statistics.status_code == 200
        for response in (
            viewer_loans,
            viewer_loan_overview,
            viewer_loan_statistics,
        ):
            _assert_no_private_loan_text(response.text)

        baseline = _snapshot(session)
        forbidden_attempts: tuple[tuple[str, Callable[[], Any]], ...] = (
            (
                "start reading",
                lambda: client.post(
                    f"{reading}/sessions/start",
                    json={"started_date": "2026-11-05"},
                    headers=headers(),
                ),
            ),
            (
                "add historical reading",
                lambda: client.post(
                    f"{reading}/sessions/historical",
                    json={
                        "started_date": "2025-01-01",
                        "finished_date": "2025-01-02",
                    },
                    headers=headers(),
                ),
            ),
            (
                "change Goodreads",
                lambda: client.put(
                    f"{reading}/goodreads/me",
                    json={"url": None},
                    headers=headers(),
                ),
            ),
            (
                "start loan",
                lambda: client.post(
                    f"{loans}/active",
                    json={"loaned_to": "Forbidden borrower"},
                    headers=headers(),
                ),
            ),
            (
                "return loan",
                lambda: client.post(
                    f"{loans}/active/return",
                    json={"returned_date": "2026-11-06"},
                    headers=headers(),
                ),
            ),
            (
                "cancel loan",
                lambda: client.delete(f"{loans}/active", headers=headers()),
            ),
            (
                "add historical loan",
                lambda: client.post(
                    f"{loans}/history",
                    json={"loaned_to": "Forbidden historical borrower"},
                    headers=headers(),
                ),
            ),
        )
        for label, attempt in forbidden_attempts:
            response = attempt()
            assert response.status_code in {403, 404}, (label, response.text)
            assert _snapshot(session) == baseline, label

    audit_details = [
        event.details
        for event in session.scalars(
            select(LibraryAuditEvent).where(
                LibraryAuditEvent.library_id == library.id
            )
        )
    ]
    serialized_audit = repr(audit_details)
    assert "A3 Secret Borrower" not in serialized_audit
    assert "A3 private address and phone" not in serialized_audit
