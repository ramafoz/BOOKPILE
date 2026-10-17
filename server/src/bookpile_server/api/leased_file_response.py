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
        async def guarded_send(message) -> None:
            self._lease_guard.ensure_owned()
            await send(message)
            self._lease_guard.ensure_owned()

        try:
            await super().__call__(scope, receive, guarded_send)
        finally:
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
