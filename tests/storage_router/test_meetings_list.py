"""GET /api/meetings list endpoint — pagination + workspace filter."""
from __future__ import annotations

from sqlalchemy import text

from storage_router.db import SessionLocal, engine
from storage_router.storage import create_artifact, create_meeting


def _seed_other_workspace() -> None:
    """ws_other is not in the migration seed; create it just for these tests."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other', 'Other') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, workspace_id, email, display_name) "
                "VALUES ('u_other', 'ws_other', 'other@tracker.local', 'Other') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )


async def test_list_returns_empty_for_unused_workspace(client) -> None:
    resp = await client.get("/api/meetings", params={"workspace_id": "ws_dev"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body == {"items": [], "total": 0}


async def test_list_filters_by_workspace(client) -> None:
    _seed_other_workspace()
    with SessionLocal() as s:
        a1 = create_artifact(
            s, workspace_id="ws_dev", source_type="pasted_transcript",
            capture_mode="imported", title="dev-1", created_by="u_dev",
            raw_text="hi",
        )
        create_meeting(s, artifact_id=a1.id, title="dev-1")
        a2 = create_artifact(
            s, workspace_id="ws_other", source_type="pasted_transcript",
            capture_mode="imported", title="other-1", created_by="u_other",
            raw_text="hi",
        )
        create_meeting(s, artifact_id=a2.id, title="other-1")
        s.commit()

    resp = await client.get("/api/meetings", params={"workspace_id": "ws_dev"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert [m["title"] for m in body["items"]] == ["dev-1"]


async def test_list_pagination(client) -> None:
    with SessionLocal() as s:
        for i in range(7):
            a = create_artifact(
                s, workspace_id="ws_dev", source_type="pasted_transcript",
                capture_mode="imported", title=f"m-{i}", created_by="u_dev",
                raw_text="hi",
            )
            create_meeting(s, artifact_id=a.id, title=f"m-{i}")
        s.commit()

    page1 = await client.get(
        "/api/meetings", params={"workspace_id": "ws_dev", "limit": 3, "offset": 0}
    )
    page2 = await client.get(
        "/api/meetings", params={"workspace_id": "ws_dev", "limit": 3, "offset": 3}
    )
    assert page1.status_code == 200 and page2.status_code == 200
    b1, b2 = page1.json(), page2.json()
    assert b1["total"] == 7 and b2["total"] == 7
    assert len(b1["items"]) == 3 and len(b2["items"]) == 3
    ids1 = {m["meeting_id"] for m in b1["items"]}
    ids2 = {m["meeting_id"] for m in b2["items"]}
    assert ids1.isdisjoint(ids2)


async def test_list_orders_newest_first(client) -> None:
    """Ordering is by artifact created_at DESC."""
    with SessionLocal() as s:
        for title in ("first", "second", "third"):
            a = create_artifact(
                s, workspace_id="ws_dev", source_type="pasted_transcript",
                capture_mode="imported", title=title, created_by="u_dev",
                raw_text="hi",
            )
            create_meeting(s, artifact_id=a.id, title=title)
            s.commit()  # commit between to get distinct created_at timestamps

    resp = await client.get("/api/meetings", params={"workspace_id": "ws_dev"})
    titles = [m["title"] for m in resp.json()["items"]]
    assert titles == ["third", "second", "first"]
