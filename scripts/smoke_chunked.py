#!/usr/bin/env python3.12
"""Mocked-Claude smoke for chunked meeting summarization.

Builds a synthetic 60-min transcript by repeating the canonical 6-segment
fixture 60 times with monotonically increasing ``start_ms``, then drives
:func:`hermes_plugin.runtime.run_chunked_extraction` against an in-process
mocked Anthropic client and a mocked storage transport.

No real API key, no real storage-router needed. This is the deterministic
counterpart to the live deploy smoke.

Usage:
    .venv/bin/python scripts/smoke_chunked.py [chunk_minutes]
"""

from __future__ import annotations

import json
import sys
from typing import Any

import httpx

from hermes_plugin.client import StorageRouterClient
from hermes_plugin.runtime import run_chunked_extraction


SEGMENT_TEMPLATE = [
    ("Alice", "Thanks for joining. Let's talk about the auth migration."),
    ("Bob", "We should delay the provider switch until staging secrets are ready."),
    ("Alice", "Agreed. Confirm we have rollback ready."),
    ("Carol", "Risk: the OAuth library version is EOL in Q4."),
    ("Bob", "I'll write the runbook by Friday."),
    ("Alice", "Open question: who owns the post-migration audit?"),
]

REPEATS = 60  # 60 minutes of synthetic content (one cycle ~= 60 s)


def _build_synthetic_transcript() -> dict:
    """6 segs x 60 cycles = 360 segs, one cycle per minute."""
    segments: list[dict] = []
    for cycle in range(REPEATS):
        cycle_base = cycle * 60_000  # one cycle per minute
        for i, (speaker, text) in enumerate(SEGMENT_TEMPLATE):
            start = cycle_base + i * 9_000  # 9s per segment, ~54s/cycle
            end = start + 8_000
            segments.append(
                {
                    "segment_id": f"seg_{cycle:03d}_{i}",
                    "speaker_id": f"speaker_{i % 3 + 1}",
                    "speaker_name": speaker,
                    "start_ms": start,
                    "end_ms": end,
                    "text": text,
                    "confidence": None,
                    "source_type": "transcript_file",
                    "is_final": True,
                }
            )
    return {"meeting_id": "m_smoke", "segments": segments}


_VALID_CARD = {
    "memory_card_id": "mc_smoke",
    "meeting_id": "m_smoke",
    "state": "draft",
    "type": "decision",
    "title": "synthetic",
    "content": "synthetic",
    "source_chunk_ids": ["seg_000_0"],
    "confidence": 0.85,
}


def _storage_handler_factory():
    posts: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST" and req.url.path == "/api/memory-cards":
            posts.append(req)
            return httpx.Response(200, json=_VALID_CARD)
        return httpx.Response(404, text=f"unexpected: {req.method} {req.url.path}")

    return handler, posts


class _MockMessages:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def create(self, **kwargs: Any):
        self.calls.append(kwargs)
        from anthropic.types import Message

        # If a tool list is bound, this is a per-chunk extraction call.
        # Emit a tool_use block (one card) followed by an end_turn next
        # call. Track per-chunk state via call_index parity.
        if kwargs.get("tools"):
            # Two-turn pattern per chunk: turn 1 = create card, turn 2 = end_turn.
            # Since we can't see turn index here, count user messages in payload.
            user_msgs = [m for m in kwargs["messages"] if m["role"] == "user"]
            if len(user_msgs) == 1:
                # First turn: emit a tool_use create_draft_memory_card block.
                payload = {
                    "id": f"msg_{len(self.calls)}",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {
                            "type": "tool_use",
                            "id": f"tu_{len(self.calls)}",
                            "name": "create_draft_memory_card",
                            "input": {
                                "meeting_id": "m_smoke",
                                "type": "decision",
                                "title": "synthetic finding",
                                "content": "x",
                                "source_chunk_ids": ["seg_000_0"],
                                "confidence": 0.8,
                            },
                        }
                    ],
                    "stop_reason": "tool_use",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
            else:
                # Follow-up turn: end_turn with topic sentence.
                payload = {
                    "id": f"msg_{len(self.calls)}",
                    "type": "message",
                    "role": "assistant",
                    "model": "claude-sonnet-4-5",
                    "content": [
                        {"type": "text", "text": "Chunk: synthetic topic."}
                    ],
                    "stop_reason": "end_turn",
                    "stop_sequence": None,
                    "usage": {"input_tokens": 1, "output_tokens": 1},
                }
        else:
            # Summary pass (no tools).
            payload = {
                "id": f"msg_{len(self.calls)}",
                "type": "message",
                "role": "assistant",
                "model": "claude-sonnet-4-5",
                "content": [
                    {"type": "text", "text": "Synthetic 5-line meeting summary."}
                ],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {"input_tokens": 1, "output_tokens": 1},
            }
        return Message.model_validate(payload)


class _MockLLM:
    def __init__(self) -> None:
        self.messages = _MockMessages()


def main(argv: list[str]) -> int:
    chunk_minutes = int(argv[1]) if len(argv) > 1 else 5

    transcript = _build_synthetic_transcript()
    print(
        f"Built synthetic transcript: {len(transcript['segments'])} segments "
        f"spanning {REPEATS} minutes."
    )

    handler, posts = _storage_handler_factory()
    client = StorageRouterClient(transport=httpx.MockTransport(handler))
    llm = _MockLLM()

    result = run_chunked_extraction(
        "m_smoke",
        chunk_minutes=chunk_minutes,
        prefetched_segments=transcript["segments"],
        client=client,
        anthropic_client=llm,
    )

    print(json.dumps(result, indent=2))
    print(f"\nMock storage POSTs: {len(posts)}")
    print(f"Mock LLM create() calls: {len(llm.messages.calls)}")

    expected_chunks = REPEATS // chunk_minutes
    assert result["chunks_processed"] == expected_chunks, (
        f"expected {expected_chunks} chunks, got {result['chunks_processed']}"
    )
    assert result["cards_created"] == expected_chunks, (
        f"expected {expected_chunks} cards (one per chunk), "
        f"got {result['cards_created']}"
    )
    assert result["summary"], "summary should be non-empty"
    print("\nSMOKE OK")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
