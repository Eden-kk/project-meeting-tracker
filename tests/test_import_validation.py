"""POST /api/conversations/import — mutual-exclusion + paste path."""
from __future__ import annotations

from sqlalchemy import select

from storage_router.db import SessionLocal
from storage_router.models.db import ConversationArtifactRow, MeetingRow


async def test_no_input_returns_400_no_input(client) -> None:
    resp = await client.post(
        "/api/conversations/import",
        data={"workspace_id": "ws_dev", "title": "empty"},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "no_input"


async def test_multiple_inputs_returns_400_multiple_inputs(client) -> None:
    resp = await client.post(
        "/api/conversations/import",
        data={"workspace_id": "ws_dev", "title": "two", "pasted_transcript": "hi"},
        files={"transcript_file": ("t.vtt", b"WEBVTT\n\nhello", "text/vtt")},
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "multiple_inputs"


async def test_pasted_transcript_path(client) -> None:
    resp = await client.post(
        "/api/conversations/import",
        data={
            "workspace_id": "ws_dev",
            "title": "paste",
            "pasted_transcript": "Alice: hi\nBob: hello",
        },
    )
    assert resp.status_code == 202, resp.text
    aid = resp.json()["artifact_id"]
    mid = resp.json()["meeting_id"]
    with SessionLocal() as s:
        row = s.execute(
            select(ConversationArtifactRow).where(ConversationArtifactRow.id == aid)
        ).scalar_one()
        assert row.source_type == "pasted_transcript"
        assert row.raw_text == "Alice: hi\nBob: hello"
        meeting = s.execute(
            select(MeetingRow).where(MeetingRow.id == mid)
        ).scalar_one()
        assert meeting.title == "paste"


async def test_title_round_trips_to_get_meeting(client) -> None:
    resp = await client.post(
        "/api/conversations/import",
        data={
            "workspace_id": "ws_dev",
            "title": "Quarterly review",
            "pasted_transcript": "hi",
        },
    )
    assert resp.status_code == 202, resp.text
    mid = resp.json()["meeting_id"]
    got = await client.get(f"/api/meetings/{mid}")
    assert got.status_code == 200, got.text
    assert got.json()["title"] == "Quarterly review"
