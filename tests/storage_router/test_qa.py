"""Hermes-backed finalize + QA route tests with monkeypatched runtime."""
from __future__ import annotations

from sqlalchemy import select

from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow, MemoryCardRow
from storage_router.storage import create_artifact, create_meeting


def _seed_meeting() -> str:
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
        return m.id


def _stub_card(meeting_id: str, **overrides) -> dict:
    base = {
        "meeting_id": meeting_id,
        "type": "decision",
        "title": "Stub decision",
        "content": "stub content",
        "source_chunk_ids": ["c1"],
        "confidence": 0.8,
    }
    base.update(overrides)
    return base


# --- finalize -------------------------------------------------------------

# 1
async def test_finalize_503_when_hermes_missing(client) -> None:
    mid = _seed_meeting()
    r = await client.post(f"/api/meetings/{mid}/finalize")
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "hermes_unavailable"


# 2
async def test_finalize_unknown_meeting_404(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization",
        lambda meeting_id, chunk_minutes=5: {"cards": [], "summary": ""},
    )
    r = await client.post("/api/meetings/m_does_not_exist/finalize")
    assert r.status_code == 404


# 3
async def test_finalize_happy_path(client, monkeypatch) -> None:
    mid = _seed_meeting()
    received: dict = {}

    def _stub(meeting_id: str, chunk_minutes: int = 5) -> dict:
        received["meeting_id"] = meeting_id
        received["chunk_minutes"] = chunk_minutes
        return {
            "cards": [
                _stub_card(meeting_id, title="One"),
                _stub_card(meeting_id, title="Two", type="action_item"),
            ],
            "summary": "It was a meeting.",
            "chunks_processed": 3,
        }

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization", _stub
    )
    r = await client.post(f"/api/meetings/{mid}/finalize")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["cards_created"] == 2
    assert body["summary"] == "It was a meeting."
    assert body["meeting_id"] == mid
    assert body["finalized_at"] is not None
    assert body["chunks_processed"] == 3
    # Default chunk_minutes propagated.
    assert received["chunk_minutes"] == 5

    with SessionLocal() as s:
        meeting = s.get(MeetingRow, mid)
        assert meeting.status == "finalized"
        assert meeting.finalized_at is not None
        rows = s.execute(
            select(MemoryCardRow).where(MemoryCardRow.meeting_id == mid)
        ).scalars().all()
        assert len(rows) == 2


# 3a — explicit chunk_minutes flows through to the runtime call
async def test_finalize_chunk_minutes_param_propagates(client, monkeypatch) -> None:
    mid = _seed_meeting()
    received: dict = {}

    def _stub(meeting_id: str, chunk_minutes: int = 5) -> dict:
        received["chunk_minutes"] = chunk_minutes
        return {"cards_created": 0, "summary": "ok", "chunks_processed": 4}

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization", _stub
    )
    r = await client.post(f"/api/meetings/{mid}/finalize?chunk_minutes=15")
    assert r.status_code == 200, r.text
    assert received["chunk_minutes"] == 15
    assert r.json()["chunks_processed"] == 4
    assert r.json()["cards_created"] == 0


# 3b — out-of-range chunk_minutes → 422
async def test_finalize_chunk_minutes_out_of_range_422(client, monkeypatch) -> None:
    mid = _seed_meeting()
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization",
        lambda meeting_id, chunk_minutes=5: {"cards": [], "summary": ""},
    )
    r = await client.post(f"/api/meetings/{mid}/finalize?chunk_minutes=0")
    assert r.status_code == 422
    r2 = await client.post(f"/api/meetings/{mid}/finalize?chunk_minutes=99")
    assert r2.status_code == 422


# 4
async def test_finalize_already_finalized_409(client, monkeypatch) -> None:
    mid = _seed_meeting()
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization",
        lambda meeting_id, chunk_minutes=5: {"cards": [], "summary": "x"},
    )
    r = await client.post(f"/api/meetings/{mid}/finalize")
    assert r.status_code == 200
    r2 = await client.post(f"/api/meetings/{mid}/finalize")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "already_finalized"


# --- qa -------------------------------------------------------------------

# 5
async def test_qa_happy_path(client, monkeypatch) -> None:
    """The route translates the plugin's raw run_skill output into the
    frontend's AskHermesResponse shape, joining [seg:<id>] citations
    against the speaker_segments table."""
    from storage_router.db import SessionLocal
    from storage_router.models.db import SpeakerSegmentRow

    mid = _seed_meeting()
    # Seed a segment so the route can resolve the [seg:c1] citation.
    with SessionLocal() as s:
        s.add(SpeakerSegmentRow(
            id="c1",
            meeting_id=mid,
            speaker_id="alice",
            speaker_name="Alice",
            start_ms=0,
            end_ms=5000,
            text="we picked Postgres",
            confidence=0.9,
            source_type="pasted_transcript",
            is_final=True,
        ))
        s.commit()

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_qa",
        lambda meeting_id, question: {
            "final_text": "Because Postgres. [seg:c1]",
            "tool_calls": [],
            "iterations": 1,
        },
    )
    r = await client.post(
        "/api/qa/meeting", json={"meeting_id": mid, "question": "Why Postgres?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "Because Postgres" in body["answer"]
    assert body["weak_evidence"] is False
    assert len(body["citations"]) == 1
    assert body["citations"][0]["segment_id"] == "c1"
    assert body["citations"][0]["speaker"] == "Alice"
    assert body["citations"][0]["text"] == "we picked Postgres"


# 6
async def test_qa_503_when_hermes_missing(client) -> None:
    mid = _seed_meeting()
    r = await client.post(
        "/api/qa/meeting", json={"meeting_id": mid, "question": "Why?"}
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "hermes_unavailable"


# 7
async def test_qa_empty_question_422(client) -> None:
    mid = _seed_meeting()
    r = await client.post(
        "/api/qa/meeting", json={"meeting_id": mid, "question": ""}
    )
    assert r.status_code == 422


# 8
async def test_qa_unknown_meeting_404(client, monkeypatch) -> None:
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_qa",
        lambda meeting_id, question: {"answer": "?", "citations": []},
    )
    r = await client.post(
        "/api/qa/meeting",
        json={"meeting_id": "m_does_not_exist", "question": "?"},
    )
    assert r.status_code == 404
