"""Phase-3 auto-finalize tests.

After `import_route` parses a meeting, the dispatcher calls
`hermes_runtime.auto_finalize_meeting(meeting_id)`. We monkeypatch the
runtime entry to assert it fires (success path) and to drive a synthetic
failure (error path -> status reverts to `ready` + last_finalize_error
populated).

The shared `_sync_background_tasks` autouse fixture in `conftest.py`
already runs FastAPI BackgroundTasks inline, so the assertions can read
the meeting row immediately after the POST returns.
"""
from __future__ import annotations

from storage_router import hermes_runtime
from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow


# 1
async def test_auto_finalize_fires_on_import(client, monkeypatch) -> None:
    seen: list[str] = []

    def _stub(meeting_id: str) -> None:
        # Mimic the contract auto_finalize_meeting honours: walk the row
        # to `finalized` so the assertion is meaningful.
        seen.append(meeting_id)
        with SessionLocal() as s:
            row = s.get(MeetingRow, meeting_id)
            assert row is not None
            row.status = "finalized"
            s.commit()

    monkeypatch.setattr(
        "storage_router.hermes_runtime.auto_finalize_meeting", _stub
    )

    r = await client.post(
        "/api/conversations/import",
        data={"workspace_id": "ws_dev", "title": "auto-finalize"},
        files={"pasted_transcript": (None, "Alice: Hi.\nBob: Hello.\n")},
    )
    assert r.status_code == 202, r.text
    meeting_id = r.json()["meeting_id"]

    # Background task ran inline; auto-finalize should have been invoked
    # exactly once and the meeting flipped to `finalized`.
    assert seen == [meeting_id]
    with SessionLocal() as s:
        row = s.get(MeetingRow, meeting_id)
        assert row.status == "finalized"
        assert row.last_finalize_error is None


# 2
async def test_auto_finalize_records_error_and_reverts_to_ready(
    client, monkeypatch
) -> None:
    """Drive _finalize_inner directly so we exercise the real status
    transitions and error-recording branch (rather than only the
    monkeypatched seam)."""

    def _bad_runtime(meeting_id: str) -> dict:
        raise RuntimeError("anthropic 429: rate limit")

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization", _bad_runtime
    )

    # Import a meeting with the auto-finalize seam stubbed so the
    # dispatcher's call is a no-op; we then drive _finalize_inner
    # ourselves to exercise the failure path explicitly.
    monkeypatch.setattr(
        "storage_router.hermes_runtime.auto_finalize_meeting", lambda mid: None
    )
    r = await client.post(
        "/api/conversations/import",
        data={"workspace_id": "ws_dev", "title": "fail-path"},
        files={"pasted_transcript": (None, "Alice: Hi.\nBob: Hello.\n")},
    )
    assert r.status_code == 202, r.text
    meeting_id = r.json()["meeting_id"]

    # Sanity: meeting is `ready` post-import.
    with SessionLocal() as s:
        assert s.get(MeetingRow, meeting_id).status == "ready"

    hermes_runtime._finalize_inner(meeting_id)

    with SessionLocal() as s:
        row = s.get(MeetingRow, meeting_id)
        assert row.status == "ready", row.status
        assert row.last_finalize_error is not None
        assert "rate limit" in row.last_finalize_error


# 3
async def test_auto_finalize_persists_returned_cards(client, monkeypatch) -> None:
    """Happy path: the runtime returns a card payload and _finalize_inner
    persists it + flips the meeting to `finalized`."""

    def _good_runtime(meeting_id: str) -> dict:
        return {
            "cards": [
                {
                    "meeting_id": meeting_id,
                    "type": "decision",
                    "title": "Adopt Postgres",
                    "content": "we picked Postgres",
                    "source_chunk_ids": ["c1"],
                    "confidence": 0.9,
                }
            ],
            "summary": "auto-finalize ok",
        }

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization", _good_runtime
    )
    monkeypatch.setattr(
        "storage_router.hermes_runtime.auto_finalize_meeting", lambda mid: None
    )

    r = await client.post(
        "/api/conversations/import",
        data={"workspace_id": "ws_dev", "title": "happy"},
        files={"pasted_transcript": (None, "Alice: Hi.\nBob: Hello.\n")},
    )
    meeting_id = r.json()["meeting_id"]

    hermes_runtime._finalize_inner(meeting_id)

    with SessionLocal() as s:
        row = s.get(MeetingRow, meeting_id)
        assert row.status == "finalized"
        assert row.finalized_at is not None
        assert row.last_finalize_error is None

    r2 = await client.get(f"/api/meetings/{meeting_id}/memory-cards")
    assert r2.status_code == 200
    assert r2.json()["total"] == 1
    assert r2.json()["items"][0]["title"] == "Adopt Postgres"
