"""GET /api/workspaces — list every workspace for the top-right switcher.

The default seed (`_ensure_dev_seed`) installs `ws_dev`; tests that need
additional workspaces seed them inline via raw SQL.
"""
from __future__ import annotations

from sqlalchemy import text

from storage_router.db import engine


def _seed_workspace(
    ws_id: str,
    name: str,
    *,
    description: str | None = None,
    last_meeting_at: str | None = None,
) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, name, description, last_meeting_at) "
                "VALUES (:id, :name, :description, :last_meeting_at) "
                "ON CONFLICT (id) DO UPDATE SET "
                "name = EXCLUDED.name, "
                "description = EXCLUDED.description, "
                "last_meeting_at = EXCLUDED.last_meeting_at"
            ),
            {
                "id": ws_id,
                "name": name,
                "description": description,
                "last_meeting_at": last_meeting_at,
            },
        )


def _wipe_workspaces_except_dev() -> None:
    """Drop extra workspaces (and dependent users) so each test starts
    clean. `ws_dev` / `u_dev` are preserved by the global seed."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM users WHERE workspace_id <> 'ws_dev'")
        )
        conn.execute(
            text("DELETE FROM workspaces WHERE id <> 'ws_dev'")
        )
        conn.execute(
            text(
                "UPDATE workspaces SET description = NULL, "
                "last_meeting_at = NULL WHERE id = 'ws_dev'"
            )
        )


async def test_returns_only_seeded_dev_workspace_by_default(client) -> None:
    _wipe_workspaces_except_dev()
    resp = await client.get("/api/workspaces")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total"] == 1
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["id"] == "ws_dev"
    assert item["description"] is None
    assert item["last_meeting_at"] is None


async def test_surfaces_description_and_last_meeting_at(client) -> None:
    _wipe_workspaces_except_dev()
    _seed_workspace(
        "ws_alpha",
        "Alpha - Q1",
        description="Product planning",
        last_meeting_at="2026-05-10T12:00:00Z",
    )
    resp = await client.get("/api/workspaces")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    alpha = next(w for w in body["items"] if w["id"] == "ws_alpha")
    assert alpha["name"] == "Alpha - Q1"
    assert alpha["description"] == "Product planning"
    assert alpha["last_meeting_at"] is not None
    _wipe_workspaces_except_dev()


async def test_sort_order_recent_first_then_nulls_last_then_name(client) -> None:
    _wipe_workspaces_except_dev()
    # Active rows sort by last_meeting_at DESC; NULL rows land at the end
    # and sort among themselves by name ASC.
    _seed_workspace("ws_recent", "Recent", last_meeting_at="2026-05-11T12:00:00Z")
    _seed_workspace("ws_stale", "Stale", last_meeting_at="2024-01-01T00:00:00Z")
    _seed_workspace("ws_zzz", "Zeta")
    _seed_workspace("ws_bbb", "Beta")

    resp = await client.get("/api/workspaces")
    assert resp.status_code == 200, resp.text
    ids = [w["id"] for w in resp.json()["items"]]
    # ws_recent -> ws_stale -> (NULL rows sorted by name:
    # Beta(ws_bbb), Dev Workspace(ws_dev), Zeta(ws_zzz)).
    assert ids[0] == "ws_recent"
    assert ids[1] == "ws_stale"
    assert ids[2:] == ["ws_bbb", "ws_dev", "ws_zzz"]
    _wipe_workspaces_except_dev()
