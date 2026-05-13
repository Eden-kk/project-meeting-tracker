"""Wave 4.2 — cross-meeting FTS search over memory_cards."""
from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import text as sql_text

from storage_router.db import SessionLocal
from storage_router.storage import (
    create_artifact,
    create_meeting,
    create_memory_card,
)


def _seed_meeting(title: str = "M1", workspace_id: str = "ws_dev", created_by: str = "u_dev") -> str:
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id=workspace_id,
            source_type="pasted_transcript",
            capture_mode="imported",
            title=title,
            created_by=created_by,
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id, title=title)
        s.commit()
        return m.id


def _seed_card(meeting_id: str, title: str, content: str, *, hidden: bool = False, type: str = "decision") -> str:
    with SessionLocal() as s:
        row = create_memory_card(
            s,
            meeting_id=meeting_id,
            type=type,
            title=title,
            content=content,
            source_chunk_ids=["c1"],
            confidence=0.85,
        )
        if hidden:
            row.hidden_at = datetime.now(UTC)
            s.flush()
        s.commit()
        return row.id


async def test_search_cards_returns_matching_titles_and_content(client) -> None:
    m = _seed_meeting("Roadmap")
    cid = _seed_card(m, "Migrate to Postgres", "We will move off SQLite by Q3.")
    _seed_card(m, "Hire infra eng", "Need someone with k8s experience.")

    r = await client.get(
        "/api/search/cards",
        params={"q": "postgres", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    hit = body["items"][0]
    assert hit["memory_card_id"] == cid
    assert hit["meeting_title"] == "Roadmap"
    assert hit["type"] == "decision"


async def test_search_cards_hidden_excluded(client) -> None:
    m = _seed_meeting()
    _seed_card(m, "Hidden secret tofu plans", "tofu", hidden=True)
    _seed_card(m, "Live tofu manifesto", "tofu")

    r = await client.get(
        "/api/search/cards",
        params={"q": "tofu", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert "Live" in body["items"][0]["title"]


async def test_search_cards_type_filter(client) -> None:
    m = _seed_meeting()
    _seed_card(m, "decide on architecture", "x", type="decision")
    _seed_card(m, "action on architecture", "x", type="action_item")

    r = await client.get(
        "/api/search/cards",
        params={"q": "architecture", "workspace_id": "ws_dev", "type": "action_item"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["type"] == "action_item"


async def test_search_cards_workspace_scoped(client) -> None:
    # ensure other workspace exists
    with SessionLocal() as s:
        s.execute(
            sql_text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other','Other') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        s.execute(
            sql_text(
                "INSERT INTO users (id, workspace_id, email, display_name) "
                "VALUES ('u_other','ws_other','o@x.test','O') ON CONFLICT (id) DO NOTHING"
            )
        )
        s.commit()
    m1 = _seed_meeting("M1")
    _seed_card(m1, "Bridge plan", "bridge plan content")
    m2 = _seed_meeting("M2", workspace_id="ws_other", created_by="u_other")
    _seed_card(m2, "Bridge plan", "different bridge plan content")

    r = await client.get(
        "/api/search/cards",
        params={"q": "bridge", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["meeting_id"] == m1


async def test_search_cards_no_q_returns_recent_by_type(client) -> None:
    """Workspace-qa's general-progress path: type filter, no q → returns
    highest-confidence / most-recent cards of that type."""
    m = _seed_meeting("Roadmap")
    _seed_card(m, "decide on theme", "x", type="decision")
    aid = _seed_card(m, "ship the SDK", "owner: Alice", type="action_item")

    r = await client.get(
        "/api/search/cards",
        params={"workspace_id": "ws_dev", "type": "action_item"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    hit = body["items"][0]
    assert hit["memory_card_id"] == aid
    assert hit["type"] == "action_item"
    assert hit["rank"] == 0.0
    assert hit["snippet"] == ""


async def test_search_cards_no_q_no_type_returns_all_recent(client) -> None:
    """No q AND no type → top cards across all types, by confidence DESC."""
    m = _seed_meeting()
    _seed_card(m, "decision one", "x", type="decision")
    _seed_card(m, "action one", "y", type="action_item")
    _seed_card(m, "pain one", "z", type="pain_point")

    r = await client.get(
        "/api/search/cards",
        params={"workspace_id": "ws_dev"},
    )
    assert r.status_code == 200
    body = r.json()
    types = {it["type"] for it in body["items"]}
    assert {"decision", "action_item", "pain_point"}.issubset(types)


async def test_search_cards_no_q_excludes_hidden(client) -> None:
    """No-q path must still honor hidden_at IS NULL."""
    m = _seed_meeting()
    _seed_card(m, "Visible action", "v", type="action_item")
    _seed_card(m, "Hidden action", "h", type="action_item", hidden=True)

    r = await client.get(
        "/api/search/cards",
        params={"workspace_id": "ws_dev", "type": "action_item"},
    )
    assert r.status_code == 200
    titles = {it["title"] for it in r.json()["items"]}
    assert "Visible action" in titles
    assert "Hidden action" not in titles


async def test_search_cards_no_q_workspace_scoped(client) -> None:
    """No-q path must respect workspace_id."""
    with SessionLocal() as s:
        s.execute(
            sql_text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other','Other') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        s.execute(
            sql_text(
                "INSERT INTO users (id, workspace_id, email, display_name) "
                "VALUES ('u_other','ws_other','o@x.test','O') ON CONFLICT (id) DO NOTHING"
            )
        )
        s.commit()
    m_other = _seed_meeting("Other", workspace_id="ws_other", created_by="u_other")
    _seed_card(m_other, "Other action", "leaked?", type="action_item")

    r = await client.get(
        "/api/search/cards",
        params={"workspace_id": "ws_dev", "type": "action_item"},
    )
    assert r.status_code == 200
    titles = {it["title"] for it in r.json()["items"]}
    assert "Other action" not in titles


async def test_search_cards_no_match_returns_empty(client) -> None:
    m = _seed_meeting()
    _seed_card(m, "Coffee", "coffee plan")
    r = await client.get(
        "/api/search/cards",
        params={"q": "nonexistxyz", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}
