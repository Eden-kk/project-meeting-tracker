"""Tests for the cross-meeting action-items + open-questions dashboards (5.1, 5.2)."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from storage_router.db import SessionLocal
from storage_router.models.db import MemoryCardRow
from storage_router.storage import (
    create_artifact,
    create_meeting,
    create_memory_card,
)


def _seed_card(
    *,
    meeting_id: str,
    type: str,
    title: str = "do thing",
    speakers: list[str] | None = None,
    hidden: bool = False,
    created_at: datetime | None = None,
) -> str:
    with SessionLocal() as s:
        card = create_memory_card(
            s,
            meeting_id=meeting_id,
            type=type,
            title=title,
            content="content",
            source_chunk_ids=["seg_001"],
            confidence=0.9,
            speakers_json=speakers,
        )
        if hidden:
            card.hidden_at = datetime.now(UTC)
        if created_at is not None:
            card.created_at = created_at
        s.commit()
        return card.id


def _seed_meeting(title: str) -> str:
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
        m = create_meeting(s, artifact_id=a.id, title=title, status="finalized")
        m.finalized_at = datetime.now(UTC)
        s.commit()
        return m.id


@pytest.mark.asyncio
async def test_action_items_returns_only_action_item_type(client):
    m1 = _seed_meeting("Sprint planning")
    _seed_card(meeting_id=m1, type="action_item", title="ship login")
    _seed_card(meeting_id=m1, type="decision", title="use postgres")

    res = await client.get("/api/action-items", params={"workspace_id": "ws_dev"})
    assert res.status_code == 200
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "action_item"
    assert body["items"][0]["meeting_title"] == "Sprint planning"
    assert body["items"][0]["meeting_finalized_at"] is not None


@pytest.mark.asyncio
async def test_action_items_hides_hidden_at_rows(client):
    m1 = _seed_meeting("M1")
    _seed_card(meeting_id=m1, type="action_item", title="visible")
    _seed_card(meeting_id=m1, type="action_item", title="hidden", hidden=True)

    res = await client.get("/api/action-items", params={"workspace_id": "ws_dev"})
    body = res.json()
    titles = [i["title"] for i in body["items"]]
    assert titles == ["visible"]


@pytest.mark.asyncio
async def test_action_items_speaker_filter(client):
    m1 = _seed_meeting("M1")
    _seed_card(meeting_id=m1, type="action_item", title="alice", speakers=["Alice"])
    _seed_card(meeting_id=m1, type="action_item", title="bob", speakers=["Bob"])

    res = await client.get(
        "/api/action-items",
        params={"workspace_id": "ws_dev", "speaker": "Alice"},
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["title"] == "alice"


@pytest.mark.asyncio
async def test_action_items_meeting_filter(client):
    m1 = _seed_meeting("M1")
    m2 = _seed_meeting("M2")
    _seed_card(meeting_id=m1, type="action_item", title="from-m1")
    _seed_card(meeting_id=m2, type="action_item", title="from-m2")

    res = await client.get(
        "/api/action-items",
        params={"workspace_id": "ws_dev", "meeting_id": m1},
    )
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["meeting_id"] == m1


@pytest.mark.asyncio
async def test_action_items_pagination(client):
    m1 = _seed_meeting("M1")
    for i in range(5):
        _seed_card(meeting_id=m1, type="action_item", title=f"a{i}")

    res = await client.get(
        "/api/action-items",
        params={"workspace_id": "ws_dev", "limit": 2, "offset": 0},
    )
    body = res.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2


@pytest.mark.asyncio
async def test_open_questions_route_uses_open_question_type(client):
    m1 = _seed_meeting("M1")
    _seed_card(meeting_id=m1, type="open_question", title="what about auth?")
    _seed_card(meeting_id=m1, type="action_item", title="ship it")

    res = await client.get("/api/open-questions", params={"workspace_id": "ws_dev"})
    body = res.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "open_question"


@pytest.mark.asyncio
async def test_action_items_workspace_scoping(client):
    """Rows from a different workspace must not bleed through."""
    # Seed a second workspace + meeting + card.
    from sqlalchemy import text
    from storage_router.db import engine
    with engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other', 'Other') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        c.execute(
            text(
                "INSERT INTO users (id, workspace_id, email, display_name) "
                "VALUES ('u_other', 'ws_other', 'o@x', 'Other') ON CONFLICT (id) DO NOTHING"
            )
        )

    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id="ws_other",
            source_type="pasted_transcript",
            capture_mode="imported",
            title="other",
            created_by="u_other",
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id, title="other m", status="finalized")
        s.commit()
        create_memory_card(
            s,
            meeting_id=m.id,
            type="action_item",
            title="other-card",
            content="x",
            source_chunk_ids=["seg_1"],
            confidence=0.9,
        )
        s.commit()

    res = await client.get("/api/action-items", params={"workspace_id": "ws_dev"})
    titles = [i["title"] for i in res.json()["items"]]
    assert "other-card" not in titles
