"""Test fixtures: live-Postgres + per-test data cleanup."""
from __future__ import annotations

from collections.abc import Iterator

import pytest
from sqlalchemy import text

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
