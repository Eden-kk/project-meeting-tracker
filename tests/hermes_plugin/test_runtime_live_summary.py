"""Wave 6.3 — tests for the rolling-summary skill loop.

``run_live_summary`` drives the ``live-meeting-summary`` skill against
a transcript-so-far and returns ``{"summary": str, "iterations": int}``.
The skill is bound to ``get_meeting_transcript`` only — anything else
must be rejected by the bounded-tool guard.
"""

from __future__ import annotations

import httpx

from hermes_plugin.runtime import run_live_summary

from .conftest import make_message


def _segments_handler(meeting_id: str = "m_live_sum") -> tuple[
    "list[tuple[str, str]]",
    "callable",
]:
    """Return (calls_log, mock-transport handler) that serves a tiny transcript."""
    calls: list[tuple[str, str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if (
            req.method == "GET"
            and req.url.path == f"/api/meetings/{meeting_id}/transcript"
        ):
            return httpx.Response(
                200,
                json={
                    "meeting_id": meeting_id,
                    "segments": [
                        {
                            "segment_id": "seg_1",
                            "speaker_id": "speaker_1",
                            "speaker_name": "Alice",
                            "start_ms": 0,
                            "end_ms": 4000,
                            "text": "Welcome. Today we're cutting the release.",
                            "confidence": None,
                            "source_type": "live_voice",
                            "is_final": False,
                        }
                    ],
                },
            )
        return httpx.Response(404, json={"detail": "not found"})

    return calls, handler


def test_live_summary_calls_transcript_then_returns_text(
    fake_anthropic, storage_client
):
    """Happy path: fetch transcript -> emit final summary text."""
    calls, handler = _segments_handler()
    client = storage_client(handler)

    scripted = [
        # Turn 1: ask for the transcript.
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "get_meeting_transcript",
                    "input": {"meeting_id": "m_live_sum"},
                }
            ],
            stop_reason="tool_use",
        ),
        # Turn 2: emit the rolling summary.
        make_message(
            content=[
                {
                    "type": "text",
                    "text": (
                        "Alice opened the meeting and confirmed today's "
                        "release cut. The team is currently aligning on "
                        "the cut's exact timing."
                    ),
                }
            ],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_live_summary(
        "m_live_sum",
        client=client,
        anthropic_client=llm,
    )
    assert "Alice" in result["summary"]
    assert result["iterations"] == 2
    assert ("GET", "/api/meetings/m_live_sum/transcript") in calls


def test_live_summary_strips_whitespace(fake_anthropic, storage_client):
    _, handler = _segments_handler()
    client = storage_client(handler)
    scripted = [
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "get_meeting_transcript",
                    "input": {"meeting_id": "m_live_sum"},
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            content=[{"type": "text", "text": "\n   trimmed body  \n\n"}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)
    result = run_live_summary(
        "m_live_sum", client=client, anthropic_client=llm
    )
    assert result["summary"] == "trimmed body"


def test_live_summary_rejects_other_tool(fake_anthropic, storage_client):
    """Skill must NOT be allowed to create cards or call any other tool."""
    _, handler = _segments_handler()
    client = storage_client(handler)
    scripted = [
        # Try to create a draft card -> bounded loop returns 403.
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "create_draft_memory_card",
                    "input": {
                        "meeting_id": "m_live_sum",
                        "type": "decision",
                        "title": "x",
                        "content": "y",
                        "source_chunk_ids": ["seg_1"],
                        "confidence": 0.5,
                    },
                }
            ],
            stop_reason="tool_use",
        ),
        # On seeing the tool_error, the model gives up and ends the turn.
        make_message(
            content=[{"type": "text", "text": "I cannot use that tool here."}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)
    result = run_live_summary(
        "m_live_sum", client=client, anthropic_client=llm
    )
    assert "cannot" in result["summary"].lower()
