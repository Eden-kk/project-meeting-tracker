"""Drive run_skill end-to-end against a fake Anthropic + mock storage transport."""

from __future__ import annotations

import httpx
import pytest

from hermes_plugin.runtime import run_skill

from .conftest import make_message


_VALID_CARD = {
    "memory_card_id": "mc_1",
    "meeting_id": "m_fixture001",
    "state": "draft",
    "type": "decision",
    "title": "t",
    "content": "c",
    "source_chunk_ids": ["seg_001"],
    "confidence": 0.9,
}


def _scripted_extraction_loop() -> list[dict]:
    """Three turns: (1) get_meeting_transcript, (2) two parallel
    create_draft_memory_card tool_use blocks, (3) end_turn with summary."""
    turn_1 = make_message(
        msg_id="msg_t1",
        content=[
            {
                "type": "tool_use",
                "id": "tu_1",
                "name": "get_meeting_transcript",
                "input": {"meeting_id": "m_fixture001"},
            }
        ],
        stop_reason="tool_use",
    )
    turn_2 = make_message(
        msg_id="msg_t2",
        content=[
            {
                "type": "tool_use",
                "id": "tu_2",
                "name": "create_draft_memory_card",
                "input": {
                    "meeting_id": "m_fixture001",
                    "type": "decision",
                    "title": "Auth migration timeline",
                    "content": "Delay provider switch until staging secrets are ready.",
                    "source_chunk_ids": ["seg_002"],
                    "confidence": 0.85,
                },
            },
            {
                "type": "tool_use",
                "id": "tu_3",
                "name": "create_draft_memory_card",
                "input": {
                    "meeting_id": "m_fixture001",
                    "type": "action_item",
                    "title": "Confirm rollback plan",
                    "content": "Confirm rollback ready before migration.",
                    "source_chunk_ids": ["seg_003"],
                    "confidence": 0.8,
                },
            },
        ],
        stop_reason="tool_use",
    )
    turn_3 = make_message(
        msg_id="msg_t3",
        content=[{"type": "text", "text": "Created 2 draft memory cards."}],
        stop_reason="end_turn",
    )
    return [turn_1, turn_2, turn_3]


def _build_storage_handler(transcript_fixture):
    """Returns (handler, posts) where posts collects every POST body."""
    posts: list[httpx.Request] = []

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/meetings/m_fixture001/transcript":
            return httpx.Response(200, json=transcript_fixture)
        if req.method == "POST" and req.url.path == "/api/memory-cards":
            posts.append(req)
            return httpx.Response(200, json=_VALID_CARD)
        # Anything else is a real test failure.
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    return handler, posts


def test_run_skill_extraction_loop(
    storage_client, fake_anthropic, transcript_fixture
):
    handler, posts = _build_storage_handler(transcript_fixture)
    client = storage_client(handler)
    llm = fake_anthropic(_scripted_extraction_loop())

    result = run_skill(
        "meeting-memory-extraction",
        meeting_id="m_fixture001",
        client=client,
        anthropic_client=llm,
    )

    assert result["iterations"] == 3
    assert len(result["tool_calls"]) == 3
    names = [c["name"] for c in result["tool_calls"]]
    assert names == [
        "get_meeting_transcript",
        "create_draft_memory_card",
        "create_draft_memory_card",
    ]
    assert len(posts) == 2
    assert result["final_text"] == "Created 2 draft memory cards."


def test_run_skill_handles_5xx_as_tool_error(
    storage_client, fake_anthropic, transcript_fixture
):
    """A 503 on POST /api/memory-cards must surface as is_error=True
    inside the loop without raising out of run_skill."""

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "GET" and req.url.path == "/api/meetings/m_fixture001/transcript":
            return httpx.Response(200, json=transcript_fixture)
        if req.method == "POST" and req.url.path == "/api/memory-cards":
            return httpx.Response(503, text="upstream down")
        raise AssertionError(f"unexpected request: {req.method} {req.url.path}")

    client = storage_client(handler)

    # Three turns: fetch transcript, attempt create (will 503), then end.
    scripted = [
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_1",
                    "name": "get_meeting_transcript",
                    "input": {"meeting_id": "m_fixture001"},
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            content=[
                {
                    "type": "tool_use",
                    "id": "tu_2",
                    "name": "create_draft_memory_card",
                    "input": {
                        "meeting_id": "m_fixture001",
                        "type": "decision",
                        "title": "x",
                        "content": "x",
                        "source_chunk_ids": ["seg_001"],
                        "confidence": 0.9,
                    },
                }
            ],
            stop_reason="tool_use",
        ),
        make_message(
            content=[{"type": "text", "text": "Storage unavailable; aborting."}],
            stop_reason="end_turn",
        ),
    ]
    llm = fake_anthropic(scripted)

    # Must not raise.
    result = run_skill(
        "meeting-memory-extraction",
        meeting_id="m_fixture001",
        client=client,
        anthropic_client=llm,
    )

    assert result["iterations"] == 3
    create_call = result["tool_calls"][1]
    assert create_call["name"] == "create_draft_memory_card"
    assert create_call["result"]["code"] == "storage_unavailable"


def test_run_skill_unknown_skill_raises(storage_client, fake_anthropic):
    client = storage_client(lambda req: httpx.Response(500))
    llm = fake_anthropic([])
    with pytest.raises(ValueError):
        run_skill("not-a-real-skill", meeting_id="m_1", client=client, anthropic_client=llm)


def test_run_skill_qa_requires_user_question(storage_client, fake_anthropic):
    client = storage_client(lambda req: httpx.Response(500))
    llm = fake_anthropic([])
    with pytest.raises(ValueError):
        run_skill("meeting-qa", meeting_id="m_1", client=client, anthropic_client=llm)
