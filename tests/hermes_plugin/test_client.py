"""Cover the four StorageRouterClient methods + 4xx/5xx mapping."""

from __future__ import annotations

import httpx
import pytest

from hermes_plugin.errors import StorageUnavailable, ToolError


def _capture(handler):
    """Wraps a handler so the test can inspect requests it received."""
    seen: list[httpx.Request] = []

    def _h(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        return handler(req)

    return _h, seen


def test_get_meeting_transcript_route(storage_client):
    handler, seen = _capture(
        lambda req: httpx.Response(200, json={"meeting_id": "m_1", "segments": []})
    )
    client = storage_client(handler)
    out = client.get_meeting_transcript("m_1")
    assert out == {"meeting_id": "m_1", "segments": []}
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/meetings/m_1/transcript"


def test_list_memory_cards_route_with_filters(storage_client):
    handler, seen = _capture(lambda req: httpx.Response(200, json={"cards": []}))
    client = storage_client(handler)
    client.list_memory_cards("m_1", type="decision", include_hidden=True)
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/api/meetings/m_1/memory-cards"
    assert dict(seen[0].url.params) == {"type": "decision", "include_hidden": "true"}


def test_list_memory_cards_route_no_filters(storage_client):
    handler, seen = _capture(lambda req: httpx.Response(200, json={"cards": []}))
    client = storage_client(handler)
    client.list_memory_cards("m_1")
    assert dict(seen[0].url.params) == {}


def test_create_memory_card_route(storage_client):
    handler, seen = _capture(
        lambda req: httpx.Response(
            200,
            json={
                "memory_card_id": "mc_1",
                "meeting_id": "m_1",
                "type": "decision",
                "title": "t",
                "content": "c",
                "source_chunk_ids": ["seg_1"],
                "confidence": 0.9,
            },
        )
    )
    client = storage_client(handler)
    payload = {"meeting_id": "m_1", "type": "decision", "title": "t"}
    client.create_memory_card(payload)
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/memory-cards"
    import json as _json

    assert _json.loads(seen[0].content.decode()) == payload


def test_finalize_meeting_route(storage_client):
    handler, seen = _capture(
        lambda req: httpx.Response(
            200,
            json={"meeting_id": "m_1", "finalized_at": "now", "committed_card_ids": []},
        )
    )
    client = storage_client(handler)
    client.finalize_meeting("m_1")
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/api/meetings/m_1/finalize"


def test_4xx_raises_tool_error(storage_client):
    handler = lambda req: httpx.Response(404, json={"code": "not_found", "message": "no such meeting"})
    client = storage_client(handler)
    with pytest.raises(ToolError) as exc:
        client.get_meeting_transcript("missing")
    assert exc.value.status_code == 404
    assert exc.value.code == "not_found"
    assert "no such meeting" in exc.value.message


def test_5xx_raises_storage_unavailable(storage_client):
    handler = lambda req: httpx.Response(503, text="upstream down")
    client = storage_client(handler)
    with pytest.raises(StorageUnavailable):
        client.get_meeting_transcript("m_1")


def test_transport_error_raises_storage_unavailable(storage_client):
    def boom(req: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope", request=req)

    client = storage_client(boom)
    with pytest.raises(StorageUnavailable):
        client.get_meeting_transcript("m_1")
