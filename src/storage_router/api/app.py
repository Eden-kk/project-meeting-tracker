"""FastAPI app factory."""
from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from sqlalchemy import text

from storage_router.api import import_route, meetings_route
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
    app = FastAPI(title="Tracker storage-router", version="0.1.0")
    app.state.blob_store = LocalFsBlobStore(settings.blob_store_dir)

    @app.on_event("startup")
    def _startup() -> None:
        _ensure_dev_seed()

    @app.get("/", include_in_schema=False)
    def _root() -> RedirectResponse:
        return RedirectResponse(url="/docs")

    app.include_router(import_route.router)
    app.include_router(meetings_route.router)
    return app
