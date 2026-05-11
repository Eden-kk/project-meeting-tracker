"""Test fixtures: live-Postgres + per-test data cleanup + httpx client."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
import pytest_asyncio
from fastapi import BackgroundTasks
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from storage_router.api.app import create_app
from storage_router.db import SessionLocal, engine

# Tables that test suites populate. Order matters for FK cleanup.
DATA_TABLES = [
    "speaker_segments",
    "participants",
    "meeting_sources",
    "meetings",
    "conversation_artifacts",
]


def _truncate_data() -> None:
    """Wipe per-meeting data created by tests; preserve schema + ws_dev/u_dev seed."""
    with engine.begin() as conn:
        conn.execute(text("TRUNCATE " + ", ".join(DATA_TABLES) + " RESTART IDENTITY CASCADE"))


@pytest.fixture(autouse=True)
def _clean_db() -> Iterator[None]:
    _truncate_data()
    yield
    _truncate_data()


@pytest.fixture
def db_session() -> Iterator:
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture(autouse=True)
def _sync_background_tasks(monkeypatch) -> None:
    """Run BackgroundTasks inline so the dispatcher finishes before assertions."""

    def _inline(self, func, *args, **kwargs):
        func(*args, **kwargs)

    monkeypatch.setattr(BackgroundTasks, "add_task", _inline)


@pytest_asyncio.fixture
async def client(tmp_path) -> AsyncClient:
    app = create_app()
    # Override blob_store to point at the per-test tmp dir.
    from storage_router.blob import LocalFsBlobStore

    app.state.blob_store = LocalFsBlobStore(tmp_path)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
