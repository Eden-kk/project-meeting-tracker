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
        lambda meeting_id: {"cards": [], "summary": ""},
    )
    r = await client.post("/api/meetings/m_does_not_exist/finalize")
    assert r.status_code == 404


# 3
async def test_finalize_happy_path(client, monkeypatch) -> None:
    mid = _seed_meeting()

    def _stub(meeting_id: str) -> dict:
        return {
            "cards": [
                _stub_card(meeting_id, title="One"),
                _stub_card(meeting_id, title="Two", type="action_item"),
            ],
            "summary": "It was a meeting.",
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

    with SessionLocal() as s:
        meeting = s.get(MeetingRow, mid)
        assert meeting.status == "finalized"
        assert meeting.finalized_at is not None
        rows = s.execute(
            select(MemoryCardRow).where(MemoryCardRow.meeting_id == mid)
        ).scalars().all()
        assert len(rows) == 2


# 4
async def test_finalize_already_finalized_409(client, monkeypatch) -> None:
    mid = _seed_meeting()
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_finalization",
        lambda meeting_id: {"cards": [], "summary": "x"},
    )
    r = await client.post(f"/api/meetings/{mid}/finalize")
    assert r.status_code == 200
    r2 = await client.post(f"/api/meetings/{mid}/finalize")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "already_finalized"


# --- qa -------------------------------------------------------------------

# 5
async def test_qa_happy_path(client, monkeypatch) -> None:
    mid = _seed_meeting()
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_meeting_qa",
        lambda meeting_id, question: {
            "answer": "Because Postgres.",
            "evidence": [
                {"chunk_id": "c1", "text": "we picked Postgres", "speaker": "alice"}
            ],
        },
    )
    r = await client.post(
        "/api/qa/meeting", json={"meeting_id": mid, "question": "Why Postgres?"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["answer"] == "Because Postgres."
    assert len(body["evidence"]) == 1
    assert body["evidence"][0]["chunk_id"] == "c1"


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
        lambda meeting_id, question: {"answer": "?", "evidence": []},
    )
    r = await client.post(
        "/api/qa/meeting",
        json={"meeting_id": "m_does_not_exist", "question": "?"},
    )
    assert r.status_code == 404
