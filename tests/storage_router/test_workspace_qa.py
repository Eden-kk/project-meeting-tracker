"""Wave 4.3 — workspace-wide Hermes QA route.

The runtime is monkeypatched so tests assert (a) the route invokes the
hermes shim, (b) [meeting:<m>:card:<c>] and [meeting:<m>:seg:<s>]
citations are parsed out of `final_text` and resolved to populated
Meeting/MemoryCard/SpeakerSegment rows in the response payload.
"""
from __future__ import annotations

from datetime import UTC, datetime

from storage_router.db import SessionLocal
from storage_router.models.db import MemoryCardRow, SpeakerSegmentRow
from storage_router.storage import (
    create_artifact,
    create_meeting,
    create_memory_card,
)


def _seed_meeting(title: str = "MTG") -> str:
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id="ws_dev",
            source_type="pasted_transcript",
            capture_mode="imported",
            title=title,
            created_by="u_dev",
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id, title=title)
        s.commit()
        return m.id


def _seed_card(meeting_id: str, title: str = "Card", content: str = "x") -> str:
    with SessionLocal() as s:
        row = create_memory_card(
            s,
            meeting_id=meeting_id,
            type="decision",
            title=title,
            content=content,
            source_chunk_ids=["c1"],
            confidence=0.9,
        )
        s.commit()
        return row.id


def _seed_segment(meeting_id: str, sid: str = "seg_test", text: str = "hello") -> str:
    with SessionLocal() as s:
        s.add(
            SpeakerSegmentRow(
                id=sid,
                meeting_id=meeting_id,
                speaker_id="alice",
                speaker_name="Alice",
                start_ms=0,
                end_ms=1000,
                text=text,
                confidence=0.9,
                source_type="pasted_transcript",
                is_final=True,
            )
        )
        s.commit()
    return sid


async def test_workspace_qa_503_when_hermes_runtime_raises(client, monkeypatch) -> None:
    from storage_router.hermes_runtime import HermesUnavailable

    def _raise(workspace_id, question):
        raise HermesUnavailable("plugin not installed")

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_workspace_qa", _raise
    )
    r = await client.post(
        "/api/qa/workspace",
        json={"workspace_id": "ws_dev", "question": "what shipped?"},
    )
    assert r.status_code == 503
    assert r.json()["error"]["code"] == "hermes_unavailable"


async def test_workspace_qa_empty_question_422(client) -> None:
    r = await client.post(
        "/api/qa/workspace",
        json={"workspace_id": "ws_dev", "question": ""},
    )
    assert r.status_code == 422


async def test_workspace_qa_resolves_card_citations(client, monkeypatch) -> None:
    mid = _seed_meeting("Architecture review")
    cid = _seed_card(mid, title="Adopt Postgres FTS", content="Decided.")

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_workspace_qa",
        lambda workspace_id, question: {
            "final_text": (
                "The team adopted Postgres FTS for cross-meeting search "
                f"[meeting:{mid}:card:{cid}]."
            ),
            "tool_calls": [],
            "iterations": 2,
        },
    )
    r = await client.post(
        "/api/qa/workspace",
        json={"workspace_id": "ws_dev", "question": "What did we choose for search?"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["weak_evidence"] is False
    assert len(body["citations"]) == 1
    cit = body["citations"][0]
    assert cit["meeting_id"] == mid
    assert cit["meeting_title"] == "Architecture review"
    assert cit["memory_card_id"] == cid
    assert cit["segment_id"] is None
    assert "Adopt Postgres" in cit["snippet"]


async def test_workspace_qa_resolves_segment_citations(client, monkeypatch) -> None:
    mid = _seed_meeting("Standup")
    sid = _seed_segment(mid, sid="seg_x1", text="we cut the release")

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_workspace_qa",
        lambda workspace_id, question: {
            "final_text": f"The release was cut [meeting:{mid}:seg:{sid}].",
            "tool_calls": [],
            "iterations": 2,
        },
    )
    r = await client.post(
        "/api/qa/workspace",
        json={"workspace_id": "ws_dev", "question": "When did we release?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["weak_evidence"] is False
    assert len(body["citations"]) == 1
    cit = body["citations"][0]
    assert cit["segment_id"] == sid
    assert cit["memory_card_id"] is None
    assert "release" in cit["snippet"]


async def test_workspace_qa_refused_marks_weak_evidence(client, monkeypatch) -> None:
    import json

    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_workspace_qa",
        lambda workspace_id, question: {
            "final_text": json.dumps({"refused": True, "reason": "weak_evidence"}),
            "tool_calls": [],
            "iterations": 3,
        },
    )
    r = await client.post(
        "/api/qa/workspace",
        json={"workspace_id": "ws_dev", "question": "who killed Roger Rabbit?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["weak_evidence"] is True
    assert body["citations"] == []


async def test_workspace_qa_no_citations_marks_weak(client, monkeypatch) -> None:
    """If the model returns prose without any [meeting:...:...] citations,
    the route treats it as weak evidence so the SPA can warn the user."""
    monkeypatch.setattr(
        "storage_router.hermes_runtime.run_workspace_qa",
        lambda workspace_id, question: {
            "final_text": "I cannot find a clear answer.",
            "tool_calls": [],
            "iterations": 1,
        },
    )
    r = await client.post(
        "/api/qa/workspace",
        json={"workspace_id": "ws_dev", "question": "?"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["weak_evidence"] is True
    assert body["citations"] == []
