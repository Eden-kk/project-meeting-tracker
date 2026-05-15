"""FastAPI app factory."""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from storage_router.api import (
    action_items_route,
    followup_route,
    import_route,
    live_route,
    meetings_route,
    memory_cards_route,
    qa_orchestrator_route,
    qa_route,
    search_route,
    workspaces_route,
)
from storage_router.blob import LocalFsBlobStore
from storage_router.config import settings
from storage_router.db import engine


def _ensure_dev_seed() -> None:
    """Idempotent upsert of ws_dev + u_dev (the migration also seeds them)."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_dev', 'Dev Workspace') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        conn.execute(
            text(
                "INSERT INTO users (id, workspace_id, email, display_name) "
                "VALUES ('u_dev', 'ws_dev', 'dev@tracker.local', 'Dev User') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )


def create_app() -> FastAPI:
    app = FastAPI(title="Tracker storage-router", version="0.7.0")
    app.add_middleware(
        CORSMiddleware,
        # Anchored alternation: each branch is fully bracketed so lookalikes
        # like "https://evil-lhr.life" do NOT match.
        allow_origin_regex=(
            r"^(?:"
            r"https?://(?:localhost|127\.0\.0\.1)(?::\d+)?"
            r"|https://[a-z0-9-]+\.trycloudflare\.com"
            r"|https://[a-z0-9-]+\.(?:lhr\.life|localhost\.run)"
            r")$"
        ),
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.blob_store = LocalFsBlobStore(settings.blob_store_dir)
    # Wave 8.3 — per-meeting sentence buffers, keyed by meeting_id. The
    # `live_route` handlers create entries on first chunk and pop them on
    # `end_live_meeting`.
    from storage_router.sentence_buffer import SentenceBuffer  # noqa: E402

    app.state.sentence_buffers: dict[str, SentenceBuffer] = {}
    # Wave 8.5/8.6 — per-meeting asyncio task registry, keyed by meeting_id;
    # each value is a {role: asyncio.Task} dict (topic-tracker, questioner,
    # gate consumer, ...). live_route + the live_* modules populate it;
    # `_shutdown` drains it. Initialised here so it always exists even when
    # no live meeting ever runs — otherwise `_shutdown` and the live_*
    # readers raise AttributeError on a freshly-started process.
    app.state.live_tasks: dict[str, dict] = {}

    @app.on_event("startup")
    def _startup() -> None:
        _ensure_dev_seed()

    @app.on_event("shutdown")
    async def _shutdown() -> None:
        # Cancel every running per-meeting task so the event loop can
        # terminate cleanly. Wave 8.6 + later waves all register their
        # tasks here.
        for bucket in list(app.state.live_tasks.values()):
            for task in bucket.values():
                if not task.done():
                    task.cancel()
        app.state.live_tasks.clear()

    app.include_router(import_route.router)
    app.include_router(live_route.router)
    app.include_router(meetings_route.router)
    app.include_router(memory_cards_route.router)
    app.include_router(qa_route.router)
    app.include_router(qa_orchestrator_route.router)
    app.include_router(action_items_route.router)
    app.include_router(followup_route.router)
    app.include_router(search_route.router)
    app.include_router(workspaces_route.router)

    # Optional: serve a built frontend SPA out of the same origin.
    # Set FRONTEND_DIST=/path/to/frontend/dist when launching to enable.
    frontend_dist = os.environ.get("FRONTEND_DIST")
    if frontend_dist and Path(frontend_dist).is_dir():
        dist_path = Path(frontend_dist)

        @app.get("/", include_in_schema=False)
        def _index() -> FileResponse:
            return FileResponse(dist_path / "index.html")

        # SPA fallback: any unknown non-/api path returns index.html so client
        # routing (react-router) can take over.
        app.mount("/assets", StaticFiles(directory=dist_path / "assets"), name="assets")

        @app.get("/{full_path:path}", include_in_schema=False)
        def _spa(full_path: str) -> FileResponse:
            if full_path.startswith("api/") or full_path == "docs" or full_path.startswith("docs/") or full_path == "openapi.json":
                # Let FastAPI's default 404 handle these
                from fastapi import HTTPException
                raise HTTPException(status_code=404, detail="Not Found")
            candidate = dist_path / full_path
            if candidate.is_file():
                return FileResponse(candidate)
            return FileResponse(dist_path / "index.html")
    else:
        @app.get("/", include_in_schema=False)
        def _root() -> RedirectResponse:
            return RedirectResponse(url="/docs")
    return app
