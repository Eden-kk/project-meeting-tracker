"""Tests for the Wave 6.1 live-capture stub routes.

Requires Postgres (same conftest as other storage_router tests). The
underlying routes do their own filesystem writes; we point them at a
``tmp_path`` directory via the ``LIVE_CHUNK_DIR`` env var so each test is
isolated.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def _redirect_chunk_dir(tmp_path, monkeypatch):
    """Point the live-route persistence at a per-test tmp dir."""
    chunk_root = tmp_path / "live-chunks"
    chunk_root.mkdir()
    monkeypatch.setenv("LIVE_CHUNK_DIR", str(chunk_root))
    # The module reads env at import time; reach in and rebind for the
    # duration of the test.
    from storage_router.api import live_route

    monkeypatch.setattr(live_route, "CHUNK_ROOT", chunk_root)
    return chunk_root


async def _create_meeting(client) -> str:
    resp = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "demo"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "live"
    assert body["meeting_id"].startswith("m_")
    assert body["artifact_id"].startswith("art_")
    return body["meeting_id"]


async def test_create_live_meeting(client) -> None:
    meeting_id = await _create_meeting(client)
    # Confirm GET /api/meetings/{id} sees status=live too.
    resp = await client.get(f"/api/meetings/{meeting_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "live"


async def test_audio_chunk_persists_blob_and_segment(
    client, _redirect_chunk_dir: Path
) -> None:
    meeting_id = await _create_meeting(client)
    payload = b"\x1a\x45\xdf\xa3" + b"fake-webm-bytes-0"

    resp = await client.post(
        f"/api/live-meetings/{meeting_id}/audio-chunk",
        files={"audio": ("chunk0.webm", io.BytesIO(payload), "audio/webm")},
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["seq"] == 0
    assert body["bytes"] == len(payload)

    # Blob lands at <root>/<meeting_id>/0.webm.
    persisted = _redirect_chunk_dir / meeting_id / "0.webm"
    assert persisted.exists()
    assert persisted.read_bytes() == payload

    # Second chunk increments seq.
    resp2 = await client.post(
        f"/api/live-meetings/{meeting_id}/audio-chunk",
        files={"audio": ("chunk1.webm", io.BytesIO(b"more"), "audio/webm")},
    )
    assert resp2.json()["seq"] == 1

    # Segments endpoint surfaces both placeholder rows in order.
    seg_resp = await client.get(f"/api/live-meetings/{meeting_id}/segments")
    assert seg_resp.status_code == 200
    seg_body = seg_resp.json()
    assert seg_body["status"] == "live"
    assert [s["text"] for s in seg_body["segments"]] == [
        "[live chunk 0 received]",
        "[live chunk 1 received]",
    ]
    assert [s["start_ms"] for s in seg_body["segments"]] == [0, 5000]


async def test_segments_since_id_pagination(client) -> None:
    meeting_id = await _create_meeting(client)
    for i in range(3):
        await client.post(
            f"/api/live-meetings/{meeting_id}/audio-chunk",
            files={"audio": (f"c{i}.webm", io.BytesIO(b"x"), "audio/webm")},
        )
    full = (await client.get(f"/api/live-meetings/{meeting_id}/segments")).json()
    assert len(full["segments"]) == 3
    cut_id = full["segments"][0]["segment_id"]
    after = (
        await client.get(
            f"/api/live-meetings/{meeting_id}/segments",
            params={"since_id": cut_id},
        )
    ).json()
    assert len(after["segments"]) == 2
    assert after["segments"][0]["segment_id"] == full["segments"][1]["segment_id"]


async def test_end_meeting_flips_to_ready(client) -> None:
    meeting_id = await _create_meeting(client)
    resp = await client.post(f"/api/live-meetings/{meeting_id}/end")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"

    # Subsequent chunk uploads are rejected with 409.
    chunk_resp = await client.post(
        f"/api/live-meetings/{meeting_id}/audio-chunk",
        files={"audio": ("c.webm", io.BytesIO(b"x"), "audio/webm")},
    )
    assert chunk_resp.status_code == 409
    assert chunk_resp.json()["detail"]["error"]["code"] == "not_live"


async def test_create_404_unknown_meeting(client) -> None:
    resp = await client.post(
        "/api/live-meetings/m_does_not_exist/audio-chunk",
        files={"audio": ("c.webm", io.BytesIO(b"x"), "audio/webm")},
    )
    assert resp.status_code == 404
