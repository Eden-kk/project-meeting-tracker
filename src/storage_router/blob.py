"""Blob storage adapter: LocalFsBlobStore (dev) + S3BlobStore stub."""
from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import BinaryIO, Protocol
from urllib.parse import urlparse

from storage_router.ids import new_id


class BlobStore(Protocol):
    def put(
        self, stream: BinaryIO, *, key_hint: str, content_type: str | None
    ) -> str: ...
    def delete(self, url: str) -> bool: ...


def _ext_for_hint(key_hint: str) -> str:
    suffix = Path(key_hint).suffix
    return suffix if suffix else ""


class LocalFsBlobStore:
    """Writes to BLOB_STORE_DIR/<yyyy>/<mm>/<id><ext>; returns file:// URL."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)

    def put(
        self, stream: BinaryIO, *, key_hint: str, content_type: str | None = None
    ) -> str:
        # The caller's UploadFile is a SpooledTemporaryFile that disappears
        # at request end; read fully and synchronously here.
        data = stream.read()
        now = datetime.now(UTC)
        sub = self.root / f"{now.year:04d}" / f"{now.month:02d}"
        sub.mkdir(parents=True, exist_ok=True)
        name = new_id("blob") + _ext_for_hint(key_hint)
        path = sub / name
        path.write_bytes(data)
        return f"file://{path.resolve()}"

    def delete(self, url: str) -> bool:
        """Best-effort unlink. Returns True if the file was removed, False
        if it was already gone, the URL didn't parse, or any IO error
        occurred. Never raises."""
        try:
            parsed = urlparse(url)
            if parsed.scheme != "file":
                return False
            path = Path(parsed.path)
            if not path.is_file():
                return False
            path.unlink()
            return True
        except OSError:
            return False


class S3BlobStore:
    """Stub for Phase 2."""

    def put(self, stream: BinaryIO, *, key_hint: str, content_type: str | None = None) -> str:
        raise NotImplementedError("phase 2")

    def delete(self, url: str) -> bool:
        raise NotImplementedError("phase 2")
