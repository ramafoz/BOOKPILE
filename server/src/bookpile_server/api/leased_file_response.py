import asyncio
from contextlib import suppress
from pathlib import Path
from time import sleep

from starlette.concurrency import run_in_threadpool
from starlette.responses import FileResponse

from ..services.operation_leases import RenewableOperationLeaseGuard


class LeaseProtectedFileResponse(FileResponse):
    """Keep an operation lease alive through the complete response stream."""

    def __init__(
        self,
        path: Path,
        guard: RenewableOperationLeaseGuard,
        **kwargs,
    ) -> None:
        super().__init__(path, **kwargs)
        self._lease_guard = guard

    async def __call__(self, scope, receive, send) -> None:
        loop = asyncio.get_running_loop()
        failure_signal = asyncio.Event()

        def signal_failure() -> None:
            try:
                loop.call_soon_threadsafe(failure_signal.set)
            except RuntimeError:
                pass

        self._lease_guard.add_failure_listener(signal_failure)
        failure_task = asyncio.create_task(failure_signal.wait())

        async def guarded_send(message) -> None:
            self._lease_guard.ensure_owned()
            send_task = asyncio.create_task(send(message))
            try:
                done, _ = await asyncio.wait(
                    (send_task, failure_task),
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if failure_task in done:
                    send_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await send_task
                    self._lease_guard.ensure_owned()
                await send_task
                self._lease_guard.ensure_owned()
            finally:
                if not send_task.done():
                    send_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await send_task

        try:
            await super().__call__(scope, receive, guarded_send)
        finally:
            self._lease_guard.remove_failure_listener(signal_failure)
            failure_task.cancel()
            with suppress(asyncio.CancelledError):
                await failure_task
            await run_in_threadpool(self._cleanup)

    def _cleanup(self) -> None:
        try:
            path = Path(self.path)
            for attempt in range(20):
                try:
                    path.unlink(missing_ok=True)
                    break
                except PermissionError:
                    if attempt == 19:
                        raise
                    sleep(0.05)
        finally:
            self._lease_guard.close()
