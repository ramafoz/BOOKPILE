from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from bookpile_server.config import Settings
from bookpile_server.models import OperationLease, SecurityEvent
from bookpile_server.repositories.operation_leases import OperationLeaseRepository
from bookpile_server.repositories.rate_limits import RateLimitRepository
from bookpile_server.services.costly_operation_leases import (
    CostlyOperationLeaseService,
    CostlyOperationLeaseUnavailableError,
)
from bookpile_server.services.operation_leases import (
    OperationLeaseManager,
)
from bookpile_server.api.leased_file_response import LeaseProtectedFileResponse


def lease_service(
    session: Session, mode: str
) -> CostlyOperationLeaseService:
    settings = Settings(
        defensive_limit_mode=mode,
        operation_lease_ttl_seconds=30,
        operation_lease_heartbeat_seconds=5,
        deployment_revision="git-lease-test",
    )
    factory = sessionmaker(bind=session.get_bind(), expire_on_commit=False)
    return CostlyOperationLeaseService(
        OperationLeaseManager(
            OperationLeaseRepository(session),
            settings.rate_limit_key_secret,
            ttl=timedelta(seconds=settings.operation_lease_ttl_seconds),
        ),
        RateLimitRepository(session),
        factory,
        settings,
    )


def test_off_mode_does_not_create_export_leases(session: Session) -> None:
    service = lease_service(session, "off")

    assert service.acquire_export(user_id=uuid4(), library_id=uuid4()) is None
    assert list(session.scalars(select(OperationLease))) == []


def test_export_guard_releases_user_and_library_leases(session: Session) -> None:
    service = lease_service(session, "enforce")

    guard = service.acquire_export(user_id=uuid4(), library_id=uuid4())
    assert guard is not None
    guard.ensure_owned()
    guard.close()

    session.expire_all()
    rows = list(session.scalars(select(OperationLease)))
    assert len(rows) == 2
    assert all(row.released_at is not None for row in rows)


def test_import_guard_fences_and_releases_user_and_library_leases(
    session: Session,
) -> None:
    service = lease_service(session, "enforce")

    guard = service.acquire_import_consolidation(
        user_id=uuid4(), library_id=uuid4()
    )
    assert guard is not None
    guard.fence(session)
    session.commit()
    guard.close()

    session.expire_all()
    rows = list(session.scalars(select(OperationLease)))
    assert {row.scope for row in rows} == {
        "import_consolidation_user",
        "import_consolidation_library",
    }
    assert all(row.released_at is not None for row in rows)


def test_enforce_mode_rejects_import_collision(session: Session) -> None:
    user_id = uuid4()
    library_id = uuid4()
    service = lease_service(session, "enforce")
    held = service.acquire_import_consolidation(
        user_id=user_id, library_id=library_id
    )
    assert held is not None
    try:
        with pytest.raises(CostlyOperationLeaseUnavailableError):
            service.acquire_import_consolidation(
                user_id=user_id, library_id=library_id
            )
    finally:
        held.close()


def test_observe_mode_records_collision_without_blocking(session: Session) -> None:
    user_id = uuid4()
    library_id = uuid4()
    service = lease_service(session, "observe")
    held = service.acquire_export(user_id=user_id, library_id=library_id)
    assert held is not None
    try:
        assert service.acquire_export(user_id=user_id, library_id=library_id) is None
    finally:
        held.close()

    event = session.scalar(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "operation_lease_observed"
        )
    )
    assert event is not None
    assert event.details["mode"] == "observe"
    assert event.details["deployment_revision"] == "git-lease-test"


def test_enforce_mode_rejects_export_collision(session: Session) -> None:
    user_id = uuid4()
    library_id = uuid4()
    service = lease_service(session, "enforce")
    held = service.acquire_export(user_id=user_id, library_id=library_id)
    assert held is not None
    try:
        with pytest.raises(CostlyOperationLeaseUnavailableError):
            service.acquire_export(user_id=user_id, library_id=library_id)
    finally:
        held.close()

    event = session.scalar(
        select(SecurityEvent).where(
            SecurityEvent.event_type == "operation_lease_blocked"
        )
    )
    assert event is not None


class RecordingGuard:
    def __init__(self, *, fail_after: int | None = None) -> None:
        self.checked = 0
        self.closed = False
        self.fail_after = fail_after
        self.failed = False
        self.listeners = set()

    def ensure_owned(self) -> None:
        self.checked += 1
        if self.failed or (
            self.fail_after is not None and self.checked >= self.fail_after
        ):
            raise RuntimeError("lease renewal failed")

    def add_failure_listener(self, listener) -> None:
        self.listeners.add(listener)
        if self.failed:
            listener()

    def remove_failure_listener(self, listener) -> None:
        self.listeners.discard(listener)

    def fail(self) -> None:
        self.failed = True
        for listener in tuple(self.listeners):
            listener()

    def close(self) -> None:
        self.closed = True


def test_leased_file_response_cleans_up_after_complete_stream(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "portable.zip"
    archive.write_bytes(b"PK synthetic archive")
    guard = RecordingGuard()
    app = FastAPI()

    @app.get("/export")
    def export():
        return LeaseProtectedFileResponse(
            archive,
            guard,  # type: ignore[arg-type]
            filename="portable.zip",
            media_type="application/zip",
        )

    with TestClient(app) as client:
        response = client.get("/export")

    assert response.status_code == 200
    assert response.content == b"PK synthetic archive"
    assert guard.closed is True
    assert not archive.exists()


def test_lease_failure_cancels_a_blocked_send(tmp_path: Path) -> None:
    archive = tmp_path / "blocked-portable.zip"
    archive.write_bytes(b"x" * 100_000)
    guard = RecordingGuard()
    response = LeaseProtectedFileResponse(
        archive,
        guard,  # type: ignore[arg-type]
        filename="portable.zip",
        media_type="application/zip",
    )

    async def invoke() -> None:
        import asyncio

        send_started = asyncio.Event()

        async def receive():
            return {"type": "http.disconnect"}

        async def blocked_send(_message) -> None:
            send_started.set()
            await asyncio.Event().wait()

        response_task = asyncio.create_task(
            response(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/export",
                    "headers": [],
                    "extensions": {},
                },
                receive,
                blocked_send,
            )
        )
        await asyncio.wait_for(send_started.wait(), timeout=1)
        guard.fail()
        with pytest.raises(RuntimeError, match="lease renewal failed"):
            await asyncio.wait_for(response_task, timeout=1)

    import anyio

    anyio.run(invoke)
    assert guard.closed is True
    assert guard.listeners == set()
    assert not archive.exists()


def test_response_cancellation_awaits_the_blocked_send_before_cleanup(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "cancelled-portable.zip"
    archive.write_bytes(b"x" * 100_000)
    guard = RecordingGuard()
    response = LeaseProtectedFileResponse(
        archive,
        guard,  # type: ignore[arg-type]
        filename="portable.zip",
        media_type="application/zip",
    )

    async def invoke() -> None:
        import asyncio

        send_started = asyncio.Event()
        send_finished = asyncio.Event()

        async def receive():
            return {"type": "http.disconnect"}

        async def blocked_send(_message) -> None:
            send_started.set()
            try:
                await asyncio.Event().wait()
            finally:
                send_finished.set()

        response_task = asyncio.create_task(
            response(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/export",
                    "headers": [],
                    "extensions": {},
                },
                receive,
                blocked_send,
            )
        )
        await asyncio.wait_for(send_started.wait(), timeout=1)
        response_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await response_task
        assert send_finished.is_set()

    import anyio

    anyio.run(invoke)
    assert guard.closed is True
    assert guard.listeners == set()
    assert not archive.exists()


def test_lease_failure_interrupts_stream_and_still_cleans_up(
    tmp_path: Path,
) -> None:
    archive = tmp_path / "slow-portable.zip"
    archive.write_bytes(b"x" * 200_000)
    guard = RecordingGuard(fail_after=5)
    response = LeaseProtectedFileResponse(
        archive,
        guard,  # type: ignore[arg-type]
        filename="portable.zip",
        media_type="application/zip",
    )

    async def invoke() -> None:
        async def receive():
            return {"type": "http.disconnect"}

        async def slow_send(_message) -> None:
            import anyio

            await anyio.sleep(0.2)

        try:
            await response(
                {
                    "type": "http",
                    "method": "GET",
                    "path": "/export",
                    "headers": [],
                    "extensions": {},
                },
                receive,
                slow_send,
            )
        except BaseException:
            return
        raise AssertionError("the failed lease should interrupt the response")

    import anyio

    anyio.run(invoke)
    assert guard.checked >= 2
    assert guard.closed is True
    assert not archive.exists()
