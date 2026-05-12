"""Route-layer tests for POST /api/qa/orchestrator. Hermes runtime is
monkeypatched so no real LLM (or DB writes to new workspace columns)
are exercised here.
"""

from __future__ import annotations

import pytest

from storage_router import hermes_runtime


@pytest.mark.asyncio
async def test_orchestrator_route_happy_shape(client, monkeypatch):
    """Route accepts {question} and returns {final_text, citations, dispatches}."""
    fake_response = {
        "final_text": "Answer with [project:ws_a:meeting:m1:card:c2].",
        "citations": [
            {"workspace_id": "ws_a", "meeting_id": "m1", "memory_card_id": "c2"}
        ],
        "dispatches": [
            {"_workspace_id": "ws_a", "summary": "...", "refused": False,
             "failed": False, "tools_called": ["search_cards"]}
        ],
    }

    monkeypatch.setattr(
        hermes_runtime,
        "run_project_orchestrator",
        lambda question: fake_response,
    )

    resp = await client.post(
        "/api/qa/orchestrator",
        json={"question": "What did Alpha decide?"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["final_text"] == fake_response["final_text"]
    assert data["citations"] == [
        {"workspace_id": "ws_a", "meeting_id": "m1",
         "memory_card_id": "c2", "segment_id": None}
    ]
    # dispatches surfaces the observability payload (incl. tools_called).
    assert data["dispatches"][0]["tools_called"] == ["search_cards"]


@pytest.mark.asyncio
async def test_orchestrator_route_malformed_body(client):
    """Empty / missing question → 422 (Pydantic validation)."""
    resp = await client.post("/api/qa/orchestrator", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_orchestrator_route_hermes_unavailable(client, monkeypatch):
    """When the plugin lookup fails we surface a 503 not a 500."""
    def _boom(_q: str):
        raise hermes_runtime.HermesUnavailable("plugin missing")

    monkeypatch.setattr(hermes_runtime, "run_project_orchestrator", _boom)
    resp = await client.post(
        "/api/qa/orchestrator", json={"question": "anything"}
    )
    assert resp.status_code == 503
    assert resp.json()["error"]["code"] == "hermes_unavailable"
