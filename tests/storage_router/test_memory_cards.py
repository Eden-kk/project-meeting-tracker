"""Memory-card create + list tests against live Postgres.

Phase-3 redesign: there is no per-card `state` enum, no `needs_review`,
and the patch/commit/reject routes are gone. The list endpoint hides
agent-soft-deleted rows (`hidden_at IS NOT NULL`) by default.
"""
from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from storage_router.db import SessionLocal
from storage_router.models.db import MemoryCardRow
from storage_router.storage import create_artifact, create_meeting


def _seed_meeting(title: str = "t") -> str:
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
        m = create_meeting(s, artifact_id=a.id)
        s.commit()
        return m.id


def _card_payload(meeting_id: str, **overrides) -> dict:
    base = {
        "meeting_id": meeting_id,
        "type": "decision",
        "title": "Adopt Postgres",
        "content": "We agreed to use Postgres for Phase 2.",
        "source_chunk_ids": ["chunk_1"],
        "confidence": 0.9,
        "speakers_json": ["alice"],
    }
    base.update(overrides)
    return base


# 1
async def test_create_card_returns_201_without_state_field(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["memory_card_id"].startswith("mem_")
    assert body["meeting_id"] == mid
    # Phase-3: state + needs_review fields are gone from the contract.
    assert "state" not in body
    assert "needs_review" not in body
    assert body["hidden_at"] is None
    assert body["superseded_by_id"] is None


# 2
async def test_create_card_unknown_meeting_404(client) -> None:
    r = await client.post(
        "/api/memory-cards", json=_card_payload("m_does_not_exist")
    )
    assert r.status_code == 404


# 3
async def test_create_card_missing_required_field_422(client) -> None:
    mid = _seed_meeting()
    payload = _card_payload(mid)
    payload.pop("title")
    r = await client.post("/api/memory-cards", json=payload)
    assert r.status_code == 422


# 4 — supplying `needs_review` (a removed field) is rejected by extra="forbid".
async def test_create_rejects_legacy_needs_review_field(client) -> None:
    mid = _seed_meeting()
    payload = _card_payload(mid)
    payload["needs_review"] = True
    r = await client.post("/api/memory-cards", json=payload)
    assert r.status_code == 422


# 5
async def test_list_filter_by_type(client) -> None:
    mid = _seed_meeting()
    await client.post("/api/memory-cards", json=_card_payload(mid, type="decision"))
    await client.post(
        "/api/memory-cards", json=_card_payload(mid, type="action_item")
    )
    r = await client.get(f"/api/meetings/{mid}/memory-cards?type=action_item")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "action_item"


# 6
async def test_list_pagination(client) -> None:
    mid = _seed_meeting()
    for i in range(3):
        r = await client.post(
            "/api/memory-cards", json=_card_payload(mid, title=f"card-{i}")
        )
        assert r.status_code == 201
    r = await client.get(f"/api/meetings/{mid}/memory-cards?limit=2&offset=0")
    body = r.json()
    assert len(body["items"]) == 2
    assert body["total"] == 3


# 7
async def test_list_unknown_meeting_404(client) -> None:
    r = await client.get("/api/meetings/m_does_not_exist/memory-cards")
    assert r.status_code == 404


# 8 — NEW: hidden_at filter excludes agent-soft-deleted rows by default;
# include_hidden=true returns them.
async def test_list_excludes_hidden_by_default(client) -> None:
    mid = _seed_meeting()
    await client.post("/api/memory-cards", json=_card_payload(mid, title="visible"))
    r2 = await client.post("/api/memory-cards", json=_card_payload(mid, title="hidden"))
    hidden_id = r2.json()["memory_card_id"]

    # Mark the second card as agent-hidden by writing directly to the DB
    # (later features will expose this through a Hermes tool).
    with SessionLocal() as s:
        row = s.execute(
            select(MemoryCardRow).where(MemoryCardRow.id == hidden_id)
        ).scalar_one()
        row.hidden_at = datetime.now(UTC)
        s.commit()

    r = await client.get(f"/api/meetings/{mid}/memory-cards")
    body = r.json()
    assert body["total"] == 1, body
    assert body["items"][0]["title"] == "visible"
    assert body["items"][0]["hidden_at"] is None

    # Opt-in to see hidden rows.
    r3 = await client.get(
        f"/api/meetings/{mid}/memory-cards?include_hidden=true"
    )
    body2 = r3.json()
    assert body2["total"] == 2
    assert {item["title"] for item in body2["items"]} == {"visible", "hidden"}


# 9 — legacy commit/reject/patch routes are gone; verify 4xx from FastAPI.
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("PATCH", "/api/memory-cards/mem_nope", {"title": "x"}),
        ("POST", "/api/memory-cards/mem_nope/commit", None),
        ("POST", "/api/memory-cards/mem_nope/reject", None),
    ],
)
async def test_legacy_routes_return_4xx(client, method, path, payload) -> None:
    if method == "PATCH":
        r = await client.patch(path, json=payload)
    else:
        r = await client.post(path)
    # FastAPI returns 405 when the verb has no handler, 404 when the
    # subpath does not exist. Either is acceptable: the route is gone.
    assert r.status_code in (404, 405), (path, r.status_code, r.text)
