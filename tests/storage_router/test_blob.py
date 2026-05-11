"""LocalFsBlobStore round-trip."""
from __future__ import annotations

import io
from urllib.parse import urlparse

from storage_router.blob import LocalFsBlobStore


def test_put_writes_bytes_and_returns_file_url(tmp_path) -> None:
    store = LocalFsBlobStore(tmp_path)
    payload = b"\x00\x01abc\xff"
    url = store.put(io.BytesIO(payload), key_hint="sample.wav", content_type="audio/wav")
    assert url.startswith("file://")
    path = urlparse(url).path
    with open(path, "rb") as f:
        assert f.read() == payload
    assert path.endswith(".wav")


def test_put_handles_no_extension(tmp_path) -> None:
    store = LocalFsBlobStore(tmp_path)
    url = store.put(io.BytesIO(b"x"), key_hint="noext", content_type=None)
    path = urlparse(url).path
    assert "blob_" in path
