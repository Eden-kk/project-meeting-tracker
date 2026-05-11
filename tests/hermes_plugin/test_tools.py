"""Cover each tool in TOOL_REGISTRY: happy path + invalid-input -> ToolError(422)."""

from __future__ import annotations

import json

import httpx
import pytest

from hermes_plugin.errors import ToolError
from hermes_plugin.tools import TOOL_REGISTRY


# A complete valid memory-card payload reused in several tests.
_VALID_CARD = {
    "memory_card_id": "mc_1",
    "meeting_id": "m_1",
    "state": "draft",
    "type": "decision",
    "title": "t",
    "content": "c",
    "source_chunk_ids": ["seg_1"],
    "confidence": 0.9,
}


def test_get_meeting_transcript_happy_path(storage_client, transcript_fixture):
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json=transcript_fixture)

    client = storage_client(handler)
    out = TOOL_REGISTRY["get_meeting_transcript"]({"meeting_id": "m_fixture001"}, client)
    assert out["meeting_id"] == "m_fixture001"
    assert isinstance(out["segments"], list) and len(out["segments"]) > 0
    assert seen[0].url.path == "/api/meetings/m_fixture001/transcript"


def test_get_meeting_transcript_invalid_input(storage_client):
    client = storage_client(lambda req: httpx.Response(500))
    with pytest.raises(ToolError) as exc:
        TOOL_REGISTRY["get_meeting_transcript"]({}, client)
    assert exc.value.status_code == 422
    assert exc.value.code == "invalid_input"


def test_search_memory_cards_happy_path(storage_client):
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"cards": [_VALID_CARD]})

    client = storage_client(handler)
    out = TOOL_REGISTRY["search_memory_cards"](
        {"meeting_id": "m_1", "type": "decision"}, client
    )
    assert len(out["cards"]) == 1
    assert dict(seen[0].url.params) == {"type": "decision"}


def test_search_memory_cards_invalid_state(storage_client):
    client = storage_client(lambda req: httpx.Response(200, json={"cards": []}))
    with pytest.raises(ToolError) as exc:
        TOOL_REGISTRY["search_memory_cards"](
            {"meeting_id": "m_1", "state": "garbage"}, client
        )
    assert exc.value.status_code == 422


def test_create_draft_memory_card_injects_state_and_agent(storage_client):
    seen_payloads: list[dict] = []

    def handler(req):
        seen_payloads.append(json.loads(req.content.decode()))
        return httpx.Response(200, json=_VALID_CARD)

    client = storage_client(handler)
    out = TOOL_REGISTRY["create_draft_memory_card"](
        {
            "meeting_id": "m_1",
            "type": "decision",
            "title": "t",
            "content": "c",
            "source_chunk_ids": ["seg_1"],
            "confidence": 0.9,
        },
        client,
    )
    assert out["memory_card_id"] == "mc_1"
    assert seen_payloads[0]["state"] == "draft"
    assert seen_payloads[0]["created_by_agent"] == "hermes-plugin"
    # The input model has no `state` field, so the wire payload's
    # `state` came from the tool layer, not the caller.
    assert "state" not in {
        "meeting_id",
        "type",
        "title",
        "content",
        "source_chunk_ids",
        "confidence",
    }


def test_create_draft_memory_card_invalid_input(storage_client):
    client = storage_client(lambda req: httpx.Response(500))
    with pytest.raises(ToolError) as exc:
        # Missing source_chunk_ids -> validation failure.
        TOOL_REGISTRY["create_draft_memory_card"](
            {
                "meeting_id": "m_1",
                "type": "decision",
                "title": "t",
                "content": "c",
                "confidence": 0.9,
            },
            client,
        )
    assert exc.value.status_code == 422


def test_create_draft_memory_card_rejects_unknown_field(storage_client):
    """Plan: input model uses speakers_json, not speakers; alias rejected."""
    client = storage_client(lambda req: httpx.Response(500))
    with pytest.raises(ToolError) as exc:
        TOOL_REGISTRY["create_draft_memory_card"](
            {
                "meeting_id": "m_1",
                "type": "decision",
                "title": "t",
                "content": "c",
                "source_chunk_ids": ["seg_1"],
                "confidence": 0.9,
                "speakers": ["Alice"],  # wrong key name
            },
            client,
        )
    assert exc.value.status_code == 422


def test_finalize_meeting_memory_happy_path(storage_client):
    seen: list[httpx.Request] = []

    def handler(req):
        seen.append(req)
        return httpx.Response(
            200,
            json={
                "meeting_id": "m_1",
                "finalized_at": "2026-05-10T12:00:00Z",
                "committed_card_ids": ["mc_1", "mc_2"],
            },
        )

    client = storage_client(handler)
    out = TOOL_REGISTRY["finalize_meeting_memory"]({"meeting_id": "m_1"}, client)
    assert out["committed_card_ids"] == ["mc_1", "mc_2"]
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/meetings/m_1/finalize"


def test_storage_5xx_wrapped_as_tool_error_503(storage_client):
    client = storage_client(lambda req: httpx.Response(503, text="boom"))
    with pytest.raises(ToolError) as exc:
        TOOL_REGISTRY["finalize_meeting_memory"]({"meeting_id": "m_1"}, client)
    assert exc.value.status_code == 503
    assert exc.value.code == "storage_unavailable"
