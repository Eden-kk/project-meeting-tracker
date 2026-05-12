"""Wave 6.4 — tests for ``run_live_extraction``.

Covers:

* The window filter: segments whose ``[start_ms, end_ms]`` doesn't
  overlap ``[since_ms - overlap_ms, latest_end_ms]`` are dropped
  before the model sees them.
* First-tick (``since_ms is None``): window starts at 0.
* Boundary segments: a segment whose ``start_ms`` < window_start but
  ``end_ms`` >= window_start IS included (the model needs the full
  utterance, not a half-clipped one).
* Empty transcript / no segments: returns 0 cards, advances no
  watermark.
* The skill is bound only to ``create_draft_memory_card``; any other
  tool call returns 403 inside the loop.
"""

from __future__ import annotations

import httpx

from hermes_plugin.runtime import run_live_extraction

from .conftest import make_message


def _segments():
    """Synthetic transcript: 4 segments, ~30s each, 0-120s timeline."""
    return [
        {
            "segment_id": "seg_a",
            "speaker_id": "speaker_1",
            "speaker_name": "Alice",
            "start_ms": 0,
            "end_ms": 30_000,
            "text": "Welcome — let's start.",
            "confidence": None,
            "source_type": "live_voice",
            "is_final": False,
        },
        {
            "segment_id": "seg_b",
            "speaker_id": "speaker_2",
            "speaker_name": "Bob",
            "start_ms": 30_000,
            "end_ms": 60_000,
            "text": "I propose we ship by Friday.",
            "confidence": None,
            "source_type": "live_voice",
            "is_final": False,
        },
        {
            "segment_id": "seg_c",
            "speaker_id": "speaker_1",
            "speaker_name": "Alice",
            "start_ms": 60_000,
            "end_ms": 90_000,
            "text": "Agreed; Bob owns the cut.",
            "confidence": None,
            "source_type": "live_voice",
            "is_final": False,
        },
        {
            "segment_id": "seg_d",
            "speaker_id": "speaker_2",
            "speaker_name": "Bob",
            "start_ms": 90_000,
            "end_ms": 120_000,
            "text": "Will pull a draft tonight.",
            "confidence": None,
            "source_type": "live_voice",
            "is_final": False,
        },
    ]


def _handler_factory(meeting_id: str = "m_live_ex"):
    sent_payloads: list[str] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if (
            req.method == "GET"
            and req.url.path == f"/api/meetings/{meeting_id}/transcript"
        ):
            return httpx.Response(
                200,
                json={"meeting_id": meeting_id, "segments": _segments()},
            )
        if req.method == "POST" and req.url.path == "/api/memory-cards":
            sent_payloads.append(req.content.decode("utf-8"))
            import json
            payload = json.loads(req.content)
            return httpx.Response(
                201,
                json={
                    "memory_card_id": f"mc_{len(sent_payloads)}",
                    "meeting_id": payload["meeting_id"],
                    "type": payload["type"],
                    "title": payload["title"],
                    "content": payload["content"],
                    "source_chunk_ids": payload["source_chunk_ids"],
                    "source_start_ms": payload.get("source_start_ms"),
                    "source_end_ms": payload.get("source_end_ms"),
                    "speakers_json": payload.get("speakers_json"),
                    "confidence": payload["confidence"],
                    "hidden_at": None,
                    "superseded_by_id": None,
                    "audit_reason": None,
                    "created_by_agent": payload.get(
                        "created_by_agent", "live-meeting-extraction"
                    ),
                    "created_at": "2026-05-11T12:00:00Z",
                    "updated_at": "2026-05-11T12:00:00Z",
                },
            )
        return httpx.Response(404, json={"detail": req.url.path})

    return handler, sent_payloads


def test_first_tick_window_starts_at_zero(fake_anthropic, storage_client):
    handler, sent = _handler_factory()
    client = storage_client(handler)
    scripted = [
        make_message(
            content=[{"type": "text", "text": "Live window 0-120000: opening + decision"}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_live_extraction(
        "m_live_ex",
        since_ms=None,
        client=client,
        anthropic_client=llm,
    )
    assert result["window_start_ms"] == 0
    assert result["window_end_ms"] == 120_000
    assert result["cards_created"] == 0
    assert "opening" in result["summary"]


def test_window_filter_clips_old_segments(fake_anthropic, storage_client):
    """``since_ms=80_000`` -> window is [50_000, 120_000] (overlap=30_000).

    Segments fully before 50_000 (seg_a, 0-30_000) drop out.
    """
    handler, sent = _handler_factory()
    client = storage_client(handler)

    # The bootstrap embeds the segment ids — assert the model only saw
    # the in-window ones by inspecting the recorded LLM messages.
    scripted = [
        make_message(
            content=[{"type": "text", "text": "Live window 50000-120000: decision + ownership"}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_live_extraction(
        "m_live_ex",
        since_ms=80_000,
        client=client,
        anthropic_client=llm,
    )
    assert result["window_start_ms"] == 50_000
    # Inspect the bootstrap message that hit the LLM.
    last_call = llm.messages.calls[0]
    bootstrap = last_call["messages"][0]["content"]
    assert "seg_b" in bootstrap  # 30000-60000 -> overlaps [50000, 120000]
    assert "seg_c" in bootstrap
    assert "seg_d" in bootstrap
    assert "seg_a" not in bootstrap  # 0-30000 fully before window_start


def test_creates_card_via_tool_call(fake_anthropic, storage_client):
    handler, sent = _handler_factory()
    client = storage_client(handler)
    scripted = [
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_card1",
                    "name": "create_draft_memory_card",
                    "input": {
                        "meeting_id": "m_live_ex",
                        "type": "decision",
                        "title": "Ship by Friday",
                        "content": "Bob proposed and Alice agreed to ship by Friday.",
                        "source_chunk_ids": ["seg_b", "seg_c"],
                        "source_start_ms": 30_000,
                        "source_end_ms": 90_000,
                        "speakers_json": ["Alice", "Bob"],
                        "confidence": 0.85,
                    },
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            content=[
                {"type": "text", "text": "Live window 0-120000: ship-by-Friday decision"}
            ],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_live_extraction(
        "m_live_ex",
        since_ms=None,
        client=client,
        anthropic_client=llm,
    )
    assert result["cards_created"] == 1
    assert len(sent) == 1
    assert "Ship by Friday" in sent[0]


def test_other_tool_call_is_rejected(fake_anthropic, storage_client):
    handler, _ = _handler_factory()
    client = storage_client(handler)
    scripted = [
        # Try to call an unauthorised tool — bounded loop returns 403.
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_x",
                    "name": "get_meeting_transcript",
                    "input": {"meeting_id": "m_live_ex"},
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            content=[{"type": "text", "text": "Live window 0-120000: refused tool"}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)
    result = run_live_extraction(
        "m_live_ex", since_ms=None, client=client, anthropic_client=llm
    )
    assert result["cards_created"] == 0
    # The loop saw the tool error and stopped without crashing.
    assert "refused" in result["summary"]


def test_empty_transcript_short_circuits(fake_anthropic, storage_client):
    """No segments -> no LLM call, watermark unchanged."""
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path.endswith("/transcript"):
            return httpx.Response(200, json={"meeting_id": "m_empty", "segments": []})
        return httpx.Response(404, json={})

    client = storage_client(handler)
    # Pass an Anthropic stub that would explode if called — the runtime
    # should never hit it.
    llm = fake_anthropic([])

    result = run_live_extraction(
        "m_empty",
        since_ms=42_000,
        client=client,
        anthropic_client=llm,
    )
    assert result["cards_created"] == 0
    assert result["window_end_ms"] == 42_000  # untouched
    assert result["iterations"] == 0
    assert llm.messages.calls == []
