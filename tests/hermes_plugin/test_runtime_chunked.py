"""End-to-end tests for chunked extraction with a mocked Anthropic client."""

from __future__ import annotations

import httpx
import pytest

import hermes_plugin
from hermes_plugin import runtime as runtime_mod
from hermes_plugin.errors import ChunkedExtractionError
from hermes_plugin.runtime import run_chunked_extraction

from .conftest import make_message


_VALID_CARD = {
    "memory_card_id": "mc_x",
    "meeting_id": "m_long001",
    "type": "decision",
    "title": "t",
    "content": "c",
    "source_chunk_ids": ["seg_001"],
    "confidence": 0.9,
}


def _seg(seg_id: str, start_ms: int | None, end_ms: int | None, speaker: str = "Alice") -> dict:
    return {
        "segment_id": seg_id,
        "speaker_id": "speaker_1",
        "speaker_name": speaker,
        "start_ms": start_ms,
        "end_ms": end_ms,
        "text": f"text for {seg_id}",
        "confidence": None,
        "source_type": "transcript_file",
        "is_final": True,
    }


def _make_chunk_turns(chunk_idx: int, chunk_count: int, n_cards: int = 2) -> list[dict]:
    """Two turns per chunk: parallel create_draft_memory_card calls then end_turn."""
    cards_blocks = [
        {
            "type": "tool_use",
            "id": f"tu_c{chunk_idx}_{i}",
            "name": "create_draft_memory_card",
            "input": {
                "meeting_id": "m_long001",
                "type": "decision",
                "title": f"chunk {chunk_idx} finding {i}",
                "content": "x",
                "source_chunk_ids": [f"seg_{chunk_idx:03d}"],
                "confidence": 0.85,
            },
        }
        for i in range(n_cards)
    ]
    return [
        make_message(
            msg_id=f"chunk{chunk_idx}_t1",
            content=cards_blocks,
            stop_reason="tool_use",
        ),
        make_message(
            msg_id=f"chunk{chunk_idx}_t2",
            content=[
                {
                    "type": "text",
                    "text": f"Chunk {chunk_idx}/{chunk_count}: covered topic {chunk_idx}.",
                }
            ],
            stop_reason="end_turn",
        ),
    ]


def _summary_turn(text: str = "Line1\nLine2\nLine3\nLine4\nLine5") -> dict:
    return make_message(
        msg_id="summary_t",
        content=[{"type": "text", "text": text}],
        stop_reason="end_turn",
    )


def _noop_audit_turn() -> dict:
    """Wave 2.1 audit pass: minimal end_turn that makes no tool calls.

    The runtime always invokes the audit pass after extraction; tests
    that don't care about audit specifics script this single noop turn
    to satisfy the loop.
    """
    return make_message(
        msg_id="audit_noop",
        content=[{"type": "text", "text": "no cards needed downgrade"}],
        stop_reason="end_turn",
    )


def _noop_consolidation_turn() -> dict:
    """Wave 2.2 consolidation pass: minimal end_turn, no merges.

    Always present once the consolidation skill is on disk; tests that
    don't care about consolidation specifics script this noop turn.
    """
    return make_message(
        msg_id="consolidation_noop",
        content=[{"type": "text", "text": "no duplicates found"}],
        stop_reason="end_turn",
    )


def _three_chunk_segments() -> list[dict]:
    """Three 5-min windows with 2 segs each → chunker produces 3 chunks."""
    out: list[dict] = []
    for window in range(3):
        base = window * 5 * 60_000
        out.append(_seg(f"seg_{window*2:03d}", base + 10_000, base + 20_000))
        out.append(_seg(f"seg_{window*2+1:03d}", base + 60_000, base + 90_000))
    return out


def _storage_handler():
    posts: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/memory-cards":
            posts.append(req)
            return httpx.Response(200, json=_VALID_CARD)
        if req.method == "GET" and req.url.path == "/api/meetings/m_long001/transcript":
            return httpx.Response(
                200,
                json={"meeting_id": "m_long001", "segments": _three_chunk_segments()},
            )
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    return handler, posts


# ---------------------------------------------------------------------------
# 1. Happy path
# ---------------------------------------------------------------------------


def test_chunked_happy_path_3_chunks(storage_client, fake_anthropic) -> None:
    handler, posts = _storage_handler()
    client = storage_client(handler)

    scripted: list[dict] = []
    for i in range(3):
        scripted.extend(_make_chunk_turns(i, 3, n_cards=2))
    scripted.append(_summary_turn())
    # Wave 2.1: audit pass runs after summary. Script a noop end_turn so
    # the runtime sees "nothing to change".
    scripted.append(_noop_audit_turn())
    # Wave 2.2: consolidation pass runs after audit.
    scripted.append(_noop_consolidation_turn())

    llm = fake_anthropic(scripted)

    result = run_chunked_extraction(
        "m_long001",
        chunk_minutes=5,
        prefetched_segments=_three_chunk_segments(),
        client=client,
        anthropic_client=llm,
    )

    assert result["chunks_processed"] == 3
    assert result["cards_created"] == 6
    assert result["summary"].startswith("Line1")
    # 3 chunks (2 turns each = 6 LLM calls) + 1 summary + 1 audit + 1 consolidation = 9
    assert len(llm.messages.calls) == 3 * 2 + 1 + 1 + 1
    assert len(posts) == 6
    # Audit + consolidation passes ran but made no changes.
    assert result["audit"]["cards_hidden"] == 0
    assert result["audit"]["cards_downgraded"] == 0
    assert result["consolidation"]["cards_merged"] == 0


# ---------------------------------------------------------------------------
# 2. Mid-run failure → ChunkedExtractionError with partial counts
# ---------------------------------------------------------------------------


def test_chunked_anthropic_failure_mid_run_raises_with_partial_counts(
    storage_client, fake_anthropic
) -> None:
    handler, posts = _storage_handler()
    client = storage_client(handler)

    class _BoomMessages:
        def __init__(self, scripted: list[dict]) -> None:
            self._scripted = list(scripted)
            self.calls: list[dict] = []

        def create(self, **kwargs):
            self.calls.append(kwargs)
            # Chunk 0 needs 2 turns. After those, raise on chunk 1's first call.
            if len(self.calls) <= 2:
                from anthropic.types import Message
                return Message.model_validate(self._scripted.pop(0))
            raise RuntimeError("simulated 5xx from Anthropic")

    class _BoomLLM:
        def __init__(self, scripted: list[dict]) -> None:
            self.messages = _BoomMessages(scripted)

    chunk0_turns = _make_chunk_turns(0, 3, n_cards=2)
    llm = _BoomLLM(chunk0_turns)

    with pytest.raises(ChunkedExtractionError) as excinfo:
        run_chunked_extraction(
            "m_long001",
            chunk_minutes=5,
            prefetched_segments=_three_chunk_segments(),
            client=client,
            anthropic_client=llm,
        )

    assert excinfo.value.chunks_processed == 1
    assert excinfo.value.cards_created == 2
    # Cards from chunk 0 made it to storage.
    assert len(posts) == 2


# ---------------------------------------------------------------------------
# 3. Untimestamped transcript → shim falls back to single-pass run_skill
# ---------------------------------------------------------------------------


def test_meeting_finalization_untimestamped_falls_back_to_run_skill(monkeypatch) -> None:
    untimestamped = [_seg("seg_001", None, None), _seg("seg_002", None, None)]

    chunked_calls: list[tuple] = []
    def _fake_chunked(*args, **kwargs):
        chunked_calls.append((args, kwargs))
        return {"cards_created": 0, "chunks_processed": 0, "summary": ""}

    skill_calls: list[dict] = []
    def _fake_run_skill(*, skill_name, meeting_id, user_question=None, client=None, **_kw):
        skill_calls.append({
            "skill_name": skill_name,
            "meeting_id": meeting_id,
            "user_question": user_question,
        })
        return {"cards_created": 0, "summary": "untimestamped path"}

    def _fake_get_transcript(args, _client):
        return {"meeting_id": args["meeting_id"], "segments": untimestamped}

    # StorageRouterClient must not actually open HTTP — patch __init__ to no-op.
    monkeypatch.setattr(
        "hermes_plugin.client.StorageRouterClient.__init__", lambda self, **_kw: None
    )
    monkeypatch.setattr(
        "hermes_plugin.runtime.run_chunked_extraction", _fake_chunked
    )
    monkeypatch.setattr(
        "hermes_plugin.runtime.run_skill", _fake_run_skill
    )
    monkeypatch.setattr(
        "hermes_plugin.tools.get_meeting_transcript", _fake_get_transcript
    )

    result = hermes_plugin.meeting_finalization("m_untimed", chunk_minutes=5)
    assert chunked_calls == []
    assert skill_calls and skill_calls[0]["skill_name"] == "meeting-finalization"
    assert result["chunks_processed"] == 1
    assert result["summary"] == "untimestamped path"


# ---------------------------------------------------------------------------
# 4. Empty transcript → no Claude calls, all-zero result
# ---------------------------------------------------------------------------


def test_chunked_empty_transcript_skips_claude(storage_client, fake_anthropic) -> None:
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/meetings/m_long001/transcript":
            return httpx.Response(
                200, json={"meeting_id": "m_long001", "segments": []}
            )
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    client = storage_client(handler)
    llm = fake_anthropic([])  # no scripted responses; will assert if called

    result = run_chunked_extraction(
        "m_long001",
        chunk_minutes=5,
        prefetched_segments=[],
        client=client,
        anthropic_client=llm,
    )

    assert result == {"cards_created": 0, "chunks_processed": 0, "summary": ""}
    assert llm.messages.calls == []


# ---------------------------------------------------------------------------
# 5. chunk_minutes propagated all the way to chunker
# ---------------------------------------------------------------------------


def test_chunk_minutes_propagated_to_chunker(monkeypatch, storage_client, fake_anthropic) -> None:
    handler, _ = _storage_handler()
    client = storage_client(handler)

    captured: dict = {}
    real_chunk_segments = runtime_mod._chunker_mod.chunk_segments

    def _spy(segments, chunk_minutes=5):
        captured["chunk_minutes"] = chunk_minutes
        return real_chunk_segments(segments, chunk_minutes=chunk_minutes)

    monkeypatch.setattr(runtime_mod._chunker_mod, "chunk_segments", _spy)

    # Build enough scripted turns. chunk_minutes=10 on the 3-chunk fixture
    # yields fewer chunks (windows are wider). With 15 minutes of content
    # split at 10-min boundaries we get 2 chunks.
    scripted: list[dict] = []
    for i in range(2):
        scripted.extend(_make_chunk_turns(i, 2, n_cards=1))
    scripted.append(_summary_turn())
    scripted.append(_noop_audit_turn())
    scripted.append(_noop_consolidation_turn())
    llm = fake_anthropic(scripted)

    run_chunked_extraction(
        "m_long001",
        chunk_minutes=10,
        prefetched_segments=_three_chunk_segments(),
        client=client,
        anthropic_client=llm,
    )

    assert captured["chunk_minutes"] == 10
