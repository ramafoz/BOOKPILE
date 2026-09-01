from pathlib import Path
from typing import Protocol


class CoverStorage(Protocol):
    def put(self, object_key: str, content: bytes) -> None: ...
    def read(self, object_key: str) -> bytes: ...
    def delete(self, object_key: str) -> None: ...


class FilesystemCoverStorage:
    """Private development storage; object keys never become public paths."""

    def __init__(self, root: Path) -> None:
        self._root = root.resolve()

    def _path(self, object_key: str) -> Path:
        if not object_key or any(part in {"", ".", ".."} for part in Path(object_key).parts):
            raise ValueError("Invalid private object key")
        path = (self._root / object_key).resolve()
        if self._root not in path.parents:
            raise ValueError("Private object key escapes its storage root")
        return path

    def put(self, object_key: str, content: bytes) -> None:
        path = self._path(object_key)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".partial")
        temporary.write_bytes(content)
        temporary.replace(path)

    def read(self, object_key: str) -> bytes:
        return self._path(object_key).read_bytes()

    def delete(self, object_key: str) -> None:
        self._path(object_key).unlink(missing_ok=True)
