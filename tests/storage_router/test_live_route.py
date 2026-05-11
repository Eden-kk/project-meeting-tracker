"""Tests for the Wave 6.1 + 6.2 live-capture routes.

Requires Postgres (same conftest as other storage_router tests). The
underlying routes do their own filesystem writes; we point them at a
``tmp_path`` directory via the ``LIVE_CHUNK_DIR`` env var so each test is
isolated. The voice-ingest call is monkeypatched to a stub that returns a
canned ``NormalizedTranscript`` so we never spin up the real STT service.
"""
from __future__ import annotations

import io
from pathlib import Path

import pytest

from storage_router.models.contracts import (
    NormalizedTranscript,
    SourceType,
    SpeakerSegment,
)


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


def _canned_transcript(meeting_id: str = "ignored") -> NormalizedTranscript:
    """Two segments that look like one ~5s chunk worth of speech.

    Timestamps are 0-based for the chunk, exactly as voice-ingest emits.
    The route under test must shift them by chunk index * CHUNK_DURATION_MS.
    """
    return NormalizedTranscript(
        meeting_id=meeting_id,
        segments=[
            SpeakerSegment(
                segment_id="s_a",
                speaker_id="speaker_1",
                speaker_name="Alice",
                start_ms=0,
                end_ms=2400,
                text="hello world",
                confidence=0.93,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
            SpeakerSegment(
                segment_id="s_b",
                speaker_id="speaker_2",
                speaker_name="Bob",
                start_ms=2500,
                end_ms=4800,
                text="hi there",
                confidence=0.88,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
        ],
    )


@pytest.fixture
def patched_transcribe(monkeypatch):
    """Replace ingest_adapter_http.transcribe_voice_file with a recording stub.

    Returns the mutable ``calls`` list so tests can assert what got passed.
    """
    from storage_router.api import live_route

    calls: list[Path] = []

    def _stub(path: Path) -> NormalizedTranscript:
        calls.append(Path(path))
        return _canned_transcript()

    monkeypatch.setattr(
        live_route.ingest_adapter_http, "transcribe_voice_file", _stub
    )
    return calls


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


async def test_audio_chunk_persists_blob_and_real_segments(
    client, _redirect_chunk_dir: Path, patched_transcribe
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
    assert body["segments_added"] == 2
    assert body["transcribed"] is True

    # Blob lands at <root>/<meeting_id>/0.webm.
    persisted = _redirect_chunk_dir / meeting_id / "0.webm"
    assert persisted.exists()
    assert persisted.read_bytes() == payload
    # voice-ingest received the persisted file path.
    assert len(patched_transcribe) == 1
    assert patched_transcribe[0] == persisted


async def test_chunk_offsets_accumulate_across_chunks(
    client, patched_transcribe
) -> None:
    meeting_id = await _create_meeting(client)
    for i in range(2):
        resp = await client.post(
            f"/api/live-meetings/{meeting_id}/audio-chunk",
            files={"audio": (f"c{i}.webm", io.BytesIO(b"data"), "audio/webm")},
        )
        assert resp.json()["seq"] == i

    seg_body = (
        await client.get(f"/api/live-meetings/{meeting_id}/segments")
    ).json()
    # Two canned segments per chunk * 2 chunks = 4 rows.
    assert len(seg_body["segments"]) == 4
    starts = [s["start_ms"] for s in seg_body["segments"]]
    # Chunk 0 -> offset 0, chunk 1 -> offset 5000. Canned segments start at
    # 0 and 2500 ms (within their own chunk). After offset:
    assert starts == [0, 2500, 5000, 7500]
    assert all(s["source_type"] == "live_voice" for s in seg_body["segments"])
    assert all(s["is_final"] is False for s in seg_body["segments"])
    # Real text propagated, not a placeholder.
    assert {s["text"] for s in seg_body["segments"]} == {"hello world", "hi there"}


async def test_voice_ingest_failure_falls_back_to_placeholder(
    client, monkeypatch
) -> None:
    from storage_router.api import live_route

    def _boom(path):
        raise RuntimeError("voice-ingest exploded")

    monkeypatch.setattr(
        live_route.ingest_adapter_http, "transcribe_voice_file", _boom
    )

    meeting_id = await _create_meeting(client)
    resp = await client.post(
        f"/api/live-meetings/{meeting_id}/audio-chunk",
        files={"audio": ("c.webm", io.BytesIO(b"data"), "audio/webm")},
    )
    assert resp.status_code == 202
    assert resp.json() == {
        "seq": 0,
        "segments_added": 1,
        "bytes": 4,
        "transcribed": False,
    }
    seg_body = (
        await client.get(f"/api/live-meetings/{meeting_id}/segments")
    ).json()
    assert len(seg_body["segments"]) == 1
    assert "transcription pending" in seg_body["segments"][0]["text"]
    assert seg_body["segments"][0]["confidence"] == 0.0


async def test_segments_since_id_pagination(client, patched_transcribe) -> None:
    meeting_id = await _create_meeting(client)
    for i in range(2):
        await client.post(
            f"/api/live-meetings/{meeting_id}/audio-chunk",
            files={"audio": (f"c{i}.webm", io.BytesIO(b"x"), "audio/webm")},
        )
    full = (await client.get(f"/api/live-meetings/{meeting_id}/segments")).json()
    # 2 segments per chunk * 2 chunks
    assert len(full["segments"]) == 4
    cut_id = full["segments"][1]["segment_id"]
    after = (
        await client.get(
            f"/api/live-meetings/{meeting_id}/segments",
            params={"since_id": cut_id},
        )
    ).json()
    assert len(after["segments"]) == 2
    assert after["segments"][0]["segment_id"] == full["segments"][2]["segment_id"]


async def test_end_meeting_flips_to_ready(client, patched_transcribe) -> None:
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
