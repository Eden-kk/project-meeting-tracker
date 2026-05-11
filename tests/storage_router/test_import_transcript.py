"""POST /api/conversations/import — transcript_file path, end-to-end."""
from __future__ import annotations

import json
from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures"


async def test_import_transcript_lifecycle(client) -> None:
    with open(FIX / "sample_transcript.vtt", "rb") as f:
        resp = await client.post(
            "/api/conversations/import",
            data={"workspace_id": "ws_dev", "title": "vtt import"},
            files={"transcript_file": ("sample_transcript.vtt", f.read(), "text/vtt")},
        )
    assert resp.status_code == 202, resp.text
    mid = resp.json()["meeting_id"]

    t = await client.get(f"/api/meetings/{mid}/transcript")
    assert t.status_code == 200
    actual = t.json()

    expected = json.loads((FIX / "expected_normalized.json").read_text())
    assert len(actual["segments"]) == len(expected["segments"])
    for a, e in zip(actual["segments"], expected["segments"], strict=True):
        # segment_id is regenerated on persist; meeting_id is the real one.
        assert a["speaker_id"] == e["speaker_id"]
        assert a["speaker_name"] == e["speaker_name"]
        assert a["start_ms"] == e["start_ms"]
        assert a["end_ms"] == e["end_ms"]
        assert a["text"] == e["text"]
        assert a["confidence"] == e["confidence"]
        assert a["source_type"] == "transcript_file"
        assert a["is_final"] == e["is_final"]
