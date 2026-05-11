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


# --- Wave 2.1 audit-pass routes -------------------------------------------


async def test_patch_confidence_updates_card(client) -> None:
    mid = _seed_meeting()
    r = await client.post("/api/memory-cards", json=_card_payload(mid))
    cid = r.json()["memory_card_id"]

    r2 = await client.patch(
        f"/api/memory-cards/{cid}/confidence",
        json={"confidence": 0.42, "reason": "speaker hedged"},
    )
    assert r2.status_code == 200
    body = r2.json()
    assert body["confidence"] == 0.42
    assert body["audit_reason"] == "speaker hedged"


async def test_patch_confidence_404(client) -> None:
    r = await client.patch(
        "/api/memory-cards/mem_nope/confidence",
        json={"confidence": 0.5},
    )
    assert r.status_code == 404


async def test_hide_card_idempotent(client) -> None:
    mid = _seed_meeting()
    cid = (await client.post("/api/memory-cards", json=_card_payload(mid))).json()[
        "memory_card_id"
    ]

    r1 = await client.post(
        f"/api/memory-cards/{cid}/hide", json={"reason": "no support"}
    )
    assert r1.status_code == 200
    first_hidden_at = r1.json()["hidden_at"]
    assert first_hidden_at is not None

    # Second call must NOT advance hidden_at (idempotency).
    r2 = await client.post(
        f"/api/memory-cards/{cid}/hide", json={"reason": "still no support"}
    )
    assert r2.status_code == 200
    assert r2.json()["hidden_at"] == first_hidden_at


# --- Wave 2.2 consolidation route -----------------------------------------


async def test_supersede_merges_source_chunks(client) -> None:
    mid = _seed_meeting()
    winner_id = (
        await client.post(
            "/api/memory-cards",
            json=_card_payload(mid, title="winner", source_chunk_ids=["c1", "c2"]),
        )
    ).json()["memory_card_id"]
    loser_id = (
        await client.post(
            "/api/memory-cards",
            json=_card_payload(mid, title="loser", source_chunk_ids=["c3"]),
        )
    ).json()["memory_card_id"]

    r = await client.post(
        f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}"
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loser_id"] == loser_id
    assert body["winner_id"] == winner_id
    assert body["winner_source_chunk_ids"] == ["c1", "c2", "c3"]

    # Loser is hidden + points at winner.
    with SessionLocal() as s:
        loser_row = s.execute(
            select(MemoryCardRow).where(MemoryCardRow.id == loser_id)
        ).scalar_one()
        assert loser_row.hidden_at is not None
        assert loser_row.superseded_by_id == winner_id


async def test_supersede_idempotent_does_not_double_append(client) -> None:
    mid = _seed_meeting()
    winner_id = (
        await client.post(
            "/api/memory-cards",
            json=_card_payload(mid, title="winner", source_chunk_ids=["c1"]),
        )
    ).json()["memory_card_id"]
    loser_id = (
        await client.post(
            "/api/memory-cards",
            json=_card_payload(mid, title="loser", source_chunk_ids=["c2"]),
        )
    ).json()["memory_card_id"]

    r1 = await client.post(
        f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}"
    )
    assert r1.status_code == 200
    assert r1.json()["winner_source_chunk_ids"] == ["c1", "c2"]

    # Second call with the same pair: storage helper returns the same
    # state (no double-append) and the route 200s. Confirm via DB.
    r2 = await client.post(
        f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}"
    )
    assert r2.status_code == 200
    assert r2.json()["winner_source_chunk_ids"] == ["c1", "c2"]


async def test_supersede_cross_meeting_409(client) -> None:
    mid_a = _seed_meeting("a")
    mid_b = _seed_meeting("b")
    winner_id = (
        await client.post("/api/memory-cards", json=_card_payload(mid_a))
    ).json()["memory_card_id"]
    loser_id = (
        await client.post("/api/memory-cards", json=_card_payload(mid_b))
    ).json()["memory_card_id"]

    r = await client.post(
        f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}"
    )
    assert r.status_code == 409, r.text


async def test_supersede_hidden_winner_409(client) -> None:
    mid = _seed_meeting()
    winner_id = (
        await client.post("/api/memory-cards", json=_card_payload(mid))
    ).json()["memory_card_id"]
    loser_id = (
        await client.post("/api/memory-cards", json=_card_payload(mid))
    ).json()["memory_card_id"]
    # Hide the winner first.
    await client.post(f"/api/memory-cards/{winner_id}/hide", json={"reason": "x"})

    r = await client.post(
        f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}"
    )
    assert r.status_code == 409


async def test_list_excludes_superseded_via_hidden_at(client) -> None:
    """A superseded loser sets hidden_at, so the default list omits it."""
    mid = _seed_meeting()
    winner_id = (
        await client.post(
            "/api/memory-cards", json=_card_payload(mid, title="winner")
        )
    ).json()["memory_card_id"]
    loser_id = (
        await client.post(
            "/api/memory-cards", json=_card_payload(mid, title="loser")
        )
    ).json()["memory_card_id"]
    await client.post(f"/api/memory-cards/{loser_id}/supersede-into/{winner_id}")

    r = await client.get(f"/api/meetings/{mid}/memory-cards")
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["memory_card_id"] == winner_id
