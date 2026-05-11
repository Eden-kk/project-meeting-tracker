"""POST /api/conversations/import — voice_file path, end-to-end."""
from __future__ import annotations

from pathlib import Path

FIX = Path(__file__).resolve().parents[1] / "fixtures"


async def test_import_voice_file_lifecycle(client) -> None:
    with open(FIX / "sample_audio.wav", "rb") as f:
        resp = await client.post(
            "/api/conversations/import",
            data={"workspace_id": "ws_dev", "title": "voice import"},
            files={"voice_file": ("sample_audio.wav", f.read(), "audio/wav")},
        )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["processing_status"] == "received"
    aid, mid = body["artifact_id"], body["meeting_id"]
    assert aid.startswith("art_") and mid.startswith("m_")

    # Background task ran inline (conftest); meeting must be ready.
    m = await client.get(f"/api/meetings/{mid}")
    assert m.status_code == 200
    assert m.json()["status"] == "ready"

    t = await client.get(f"/api/meetings/{mid}/transcript")
    assert t.status_code == 200
    body = t.json()
    assert body["meeting_id"] == mid
    assert len(body["segments"]) == 6
    assert {s["source_type"] for s in body["segments"]} == {"voice_file"}
