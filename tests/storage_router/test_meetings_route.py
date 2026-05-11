"""GET /api/meetings/{id} and /transcript edge cases."""
from __future__ import annotations

from storage_router.db import SessionLocal
from storage_router.storage import create_artifact, create_meeting


async def test_get_meeting_404(client) -> None:
    resp = await client.get("/api/meetings/m_does_not_exist")
    assert resp.status_code == 404


async def test_get_transcript_409_when_processing(client) -> None:
    # Create an artifact + meeting in 'processing' WITHOUT running the dispatcher.
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id="ws_dev",
            source_type="pasted_transcript",
            capture_mode="imported",
            title="t",
            created_by="u_dev",
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id)
        s.commit()
        mid = m.id

    resp = await client.get(f"/api/meetings/{mid}/transcript")
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "not_ready"
    assert body["error"]["current_status"] == "processing"
