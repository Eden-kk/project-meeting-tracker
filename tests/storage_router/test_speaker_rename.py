"""Wave 8.4 — PATCH /api/meetings/{id}/speakers + segment-read application.

Confirms the body model accepts both the wire alias (`from`) and the
Python name (`from_`) thanks to `populate_by_name=True`, that the JSONB
map persists, and that GET /segments applies the map at read time.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from storage_router.api.meetings_route import SpeakerRenameBody
from storage_router.models.contracts import (
    NormalizedTranscript,
    SourceType,
    SpeakerSegment,
)


def test_rename_body_accepts_wire_alias():
    body = SpeakerRenameBody.model_validate({"from": "speaker_2", "to": "Alice"})
    assert body.from_ == "speaker_2"
    assert body.to == "Alice"


def test_rename_body_accepts_python_name():
    body = SpeakerRenameBody(from_="speaker_3", to="Bob")
    assert body.from_ == "speaker_3"
    assert body.to == "Bob"


def test_rename_body_rejects_unknown_field():
    with pytest.raises(ValueError):
        SpeakerRenameBody.model_validate(
            {"from": "speaker_1", "to": "Alice", "extra": "nope"}
        )


def _canned_two_speakers() -> NormalizedTranscript:
    return NormalizedTranscript(
        meeting_id="ignored",
        segments=[
            SpeakerSegment(
                segment_id="s_a",
                speaker_id="speaker_1",
                speaker_name=None,
                start_ms=0,
                end_ms=2400,
                text="hello.",
                confidence=0.9,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
            SpeakerSegment(
                segment_id="s_b",
                speaker_id="speaker_2",
                speaker_name=None,
                start_ms=2500,
                end_ms=4800,
                text="hi back.",
                confidence=0.9,
                source_type=SourceType.voice_file,
                is_final=True,
            ),
        ],
    )


@pytest.fixture(autouse=True)
def _redirect_chunk_dir(tmp_path, monkeypatch):
    chunk_root = tmp_path / "live-chunks"
    chunk_root.mkdir()
    from storage_router.api import live_route

    monkeypatch.setattr(live_route, "CHUNK_ROOT", chunk_root)


@pytest.fixture
def patched_transcribe(monkeypatch):
    from storage_router.api import live_route

    def _stub(path: Path) -> NormalizedTranscript:
        return _canned_two_speakers()

    monkeypatch.setattr(
        live_route.ingest_adapter_http, "transcribe_voice_file", _stub
    )


async def test_patch_speakers_persists_and_segments_apply_at_read_time(
    client, patched_transcribe
) -> None:
    # Arrange: create a live meeting, push one chunk so two segments exist.
    create = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "rename demo"},
    )
    meeting_id = create.json()["meeting_id"]
    await client.post(
        f"/api/live-meetings/{meeting_id}/audio-chunk",
        files={"audio": ("c0.webm", io.BytesIO(b"x"), "audio/webm")},
    )
    pre = (await client.get(f"/api/live-meetings/{meeting_id}/segments")).json()
    # Both segments started with no friendly name.
    assert all(s["speaker_name"] is None for s in pre["segments"])

    # Act: rename speaker_2 -> "Alice".
    rename = await client.patch(
        f"/api/meetings/{meeting_id}/speakers",
        json={"from": "speaker_2", "to": "Alice"},
    )
    assert rename.status_code == 200, rename.text
    body = rename.json()
    assert body["speaker_label_map"] == {"speaker_2": "Alice"}

    # Assert: GET /segments now reflects the friendly name on speaker_2.
    post = (await client.get(f"/api/live-meetings/{meeting_id}/segments")).json()
    by_speaker = {s["speaker_id"]: s["speaker_name"] for s in post["segments"]}
    assert by_speaker["speaker_1"] is None
    assert by_speaker["speaker_2"] == "Alice"

    # GET /api/meetings/{id} also surfaces the map (contracts wired up).
    meeting_resp = (await client.get(f"/api/meetings/{meeting_id}")).json()
    assert meeting_resp["speaker_label_map"] == {"speaker_2": "Alice"}


async def test_patch_speakers_404_on_unknown_meeting(client) -> None:
    r = await client.patch(
        "/api/meetings/m_does_not_exist/speakers",
        json={"from": "speaker_1", "to": "Alice"},
    )
    assert r.status_code == 404


async def test_patch_speakers_idempotent_overwrite(
    client, patched_transcribe
) -> None:
    create = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "overwrite demo"},
    )
    meeting_id = create.json()["meeting_id"]
    await client.post(
        f"/api/live-meetings/{meeting_id}/audio-chunk",
        files={"audio": ("c.webm", io.BytesIO(b"x"), "audio/webm")},
    )

    r1 = await client.patch(
        f"/api/meetings/{meeting_id}/speakers",
        json={"from": "speaker_2", "to": "Alice"},
    )
    assert r1.json()["speaker_label_map"] == {"speaker_2": "Alice"}

    r2 = await client.patch(
        f"/api/meetings/{meeting_id}/speakers",
        json={"from": "speaker_2", "to": "Alicia"},
    )
    assert r2.json()["speaker_label_map"] == {"speaker_2": "Alicia"}
