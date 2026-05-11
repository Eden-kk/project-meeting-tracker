"""Memory-card CRUD + state-transition tests against live Postgres."""
from __future__ import annotations

import pytest

from storage_router.db import SessionLocal
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
async def test_create_card_returns_201_and_draft(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["memory_card_id"].startswith("mem_")
    assert body["state"] == "draft"
    assert body["meeting_id"] == mid


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


# 4
async def test_list_filter_by_state(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    cid = r.json()["memory_card_id"]
    # commit one card so we have a non-draft.
    await client.post(f"/api/memory-cards/{cid}/commit")
    # add another that stays draft.
    await client.post("/api/memory-cards", json=_card_payload(mid, title="x"))

    r = await client.get(f"/api/meetings/{mid}/memory-cards?state=draft")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert all(item["state"] == "draft" for item in body["items"])


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
async def test_list_combined_filter_intersection(client) -> None:
    mid = _seed_meeting()
    # draft + decision (target)
    await client.post("/api/memory-cards", json=_card_payload(mid, type="decision"))
    # draft + action_item
    await client.post(
        "/api/memory-cards", json=_card_payload(mid, type="action_item")
    )
    # committed + decision
    r = await client.post(
        "/api/memory-cards", json=_card_payload(mid, type="decision", title="x")
    )
    cid = r.json()["memory_card_id"]
    await client.post(f"/api/memory-cards/{cid}/commit")

    r = await client.get(
        f"/api/meetings/{mid}/memory-cards?type=decision&state=draft"
    )
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "decision"
    assert body["items"][0]["state"] == "draft"


# 7
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


# 8
async def test_list_unknown_meeting_404(client) -> None:
    r = await client.get("/api/meetings/m_does_not_exist/memory-cards")
    assert r.status_code == 404


# 9
async def test_patch_draft_ok_advances_updated_at(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    created = r.json()
    cid = created["memory_card_id"]

    r = await client.patch(
        f"/api/memory-cards/{cid}", json={"title": "Adopt Postgres v2"}
    )
    assert r.status_code == 200, r.text
    patched = r.json()
    assert patched["title"] == "Adopt Postgres v2"
    assert patched["updated_at"] >= created["updated_at"]


# 10
async def test_patch_partial_preserves_untouched(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    original = r.json()
    cid = original["memory_card_id"]

    r = await client.patch(
        f"/api/memory-cards/{cid}", json={"title": "renamed"}
    )
    after = r.json()
    assert after["content"] == original["content"]
    assert after["confidence"] == original["confidence"]
    assert after["speakers_json"] == original["speakers_json"]


# 11
async def test_patch_state_field_is_422(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    cid = r.json()["memory_card_id"]
    r = await client.patch(
        f"/api/memory-cards/{cid}", json={"state": "committed"}
    )
    assert r.status_code == 422


# 12
async def test_patch_committed_is_409(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    cid = r.json()["memory_card_id"]
    await client.post(f"/api/memory-cards/{cid}/commit")
    r = await client.patch(f"/api/memory-cards/{cid}", json={"title": "nope"})
    assert r.status_code == 409
    body = r.json()
    assert body["error"]["code"] == "illegal_transition"
    assert body["error"]["from"] == "draft"
    assert body["error"]["to"] == "committed"


# 13
async def test_double_commit_409(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    cid = r.json()["memory_card_id"]
    r1 = await client.post(f"/api/memory-cards/{cid}/commit")
    assert r1.status_code == 200
    r2 = await client.post(f"/api/memory-cards/{cid}/commit")
    assert r2.status_code == 409
    assert r2.json()["error"]["code"] == "illegal_transition"


# 14
async def test_reject_then_commit_409(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    cid = r.json()["memory_card_id"]
    r1 = await client.post(f"/api/memory-cards/{cid}/reject")
    assert r1.status_code == 200
    assert r1.json()["state"] == "rejected"
    r2 = await client.post(f"/api/memory-cards/{cid}/commit")
    assert r2.status_code == 409


# 15
async def test_commit_clears_needs_review(client) -> None:
    mid = _seed_meeting()
    r = await client.post(
        "/api/memory-cards", json=_card_payload(mid, needs_review=True)
    )
    assert r.json()["needs_review"] is True
    cid = r.json()["memory_card_id"]
    r = await client.post(f"/api/memory-cards/{cid}/commit")
    assert r.status_code == 200
    assert r.json()["needs_review"] is False


# 16
@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("PATCH", "/api/memory-cards/mem_nope", {"title": "x"}),
        ("POST", "/api/memory-cards/mem_nope/commit", None),
        ("POST", "/api/memory-cards/mem_nope/reject", None),
    ],
)
async def test_unknown_card_404(client, method, path, payload) -> None:
    if method == "PATCH":
        r = await client.patch(path, json=payload)
    else:
        r = await client.post(path)
    assert r.status_code == 404
