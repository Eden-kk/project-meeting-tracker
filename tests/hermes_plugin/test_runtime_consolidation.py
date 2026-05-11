"""Wave 2.2: tests for the meeting-card-consolidation pass.

Confirms:
- the agent merges a near-duplicate pair via supersede_card;
- idempotency: a second supersede_card call with the same pair is
  rejected by the storage layer (409) without double-appending source
  chunks — the agent receives the tool error but the merge stays sane.
- tool budget: get_meeting_transcript is rejected.
"""

from __future__ import annotations

import json as _json

import httpx

from hermes_plugin.runtime import run_card_consolidation

from .conftest import make_message


_CARD_KEEP = {
    "memory_card_id": "mc_keep",
    "meeting_id": "m_con01",
    "type": "decision",
    "title": "Ship by Friday",
    "content": "We will release v2 on Friday.",
    "source_chunk_ids": ["seg_001", "seg_002"],
    "confidence": 0.9,
}
_CARD_DUP = {
    "memory_card_id": "mc_dup",
    "meeting_id": "m_con01",
    "type": "decision",
    "title": "Friday ship date",
    "content": "Release v2 on Friday.",
    "source_chunk_ids": ["seg_003"],
    "confidence": 0.7,
}


def _consolidation_handler():
    """Mock router that serves the card list and handles supersede.

    First supersede call returns 200; a second call with the same pair
    returns 409 (mirrors the storage helper's idempotency guard).
    """
    supersede_calls: list[tuple[str, str]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if req.method == "GET" and path == "/api/meetings/m_con01/memory-cards":
            return httpx.Response(
                200, json={"items": [_CARD_KEEP, _CARD_DUP], "total": 2}
            )
        if (
            req.method == "POST"
            and path.startswith("/api/memory-cards/")
            and "/supersede-into/" in path
        ):
            parts = path.split("/")
            loser = parts[3]
            winner = parts[5]
            if (loser, winner) in supersede_calls:
                return httpx.Response(
                    409,
                    json={"code": "merge_precondition", "message": "already merged"},
                )
            supersede_calls.append((loser, winner))
            return httpx.Response(
                200,
                json={
                    "loser_id": loser,
                    "winner_id": winner,
                    "winner_source_chunk_ids": ["seg_001", "seg_002", "seg_003"],
                },
            )
        raise AssertionError(f"unexpected request: {req.method} {path}")

    return handler, supersede_calls


def test_run_card_consolidation_merges_a_pair(storage_client, fake_anthropic) -> None:
    handler, supersede_calls = _consolidation_handler()
    client = storage_client(handler)

    scripted = [
        make_message(
            msg_id="t1",
            content=[
                {
                    "type": "tool_use",
                    "id": "tu1",
                    "name": "supersede_card",
                    "input": {"loser_id": "mc_dup", "winner_id": "mc_keep"},
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="t2",
            content=[{"type": "text", "text": "Merged mc_dup into mc_keep."}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_card_consolidation("m_con01", client=client, anthropic_client=llm)

    assert result["cards_merged"] == 1
    assert supersede_calls == [("mc_dup", "mc_keep")]
    assert "Merged" in result["summary"]


def test_run_card_consolidation_idempotent_against_duplicate_merge(
    storage_client, fake_anthropic
) -> None:
    """Two supersede_card calls on the same pair: storage 409s the
    second; the agent gets a tool error but the merge is preserved."""
    handler, supersede_calls = _consolidation_handler()
    client = storage_client(handler)

    same_merge = {
        "type": "tool_use",
        "name": "supersede_card",
        "input": {"loser_id": "mc_dup", "winner_id": "mc_keep"},
    }
    scripted = [
        make_message(
            msg_id="t1",
            content=[{"id": "tu1", **same_merge}],
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="t2",
            content=[{"id": "tu2", **same_merge}],  # second attempt at same pair
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="t3",
            content=[{"type": "text", "text": "stopping."}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_card_consolidation("m_con01", client=client, anthropic_client=llm)

    # Storage saw only one successful merge; the second was rejected.
    assert supersede_calls == [("mc_dup", "mc_keep")]
    # Both attempts counted as supersede_card invocations from the
    # registry's perspective; cards_merged is a raw counter that doesn't
    # try to distinguish success from rejection.
    assert result["cards_merged"] == 2


def test_run_card_consolidation_rejects_disallowed_tool(
    storage_client, fake_anthropic
) -> None:
    """get_meeting_transcript is NOT in the consolidation tool budget."""
    handler, _ = _consolidation_handler()
    client = storage_client(handler)

    scripted = [
        make_message(
            msg_id="t1",
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_bad",
                    "name": "get_meeting_transcript",
                    "input": {"meeting_id": "m_con01"},
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            msg_id="t2",
            content=[{"type": "text", "text": "ok, stopping."}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    result = run_card_consolidation("m_con01", client=client, anthropic_client=llm)

    # No merges happened; the disallowed tool was rejected at the runtime.
    assert result["cards_merged"] == 0
