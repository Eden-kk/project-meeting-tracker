"""Tests for the Wave 6.3 periodic agent loop in ``live_extraction``.

The scheduler exposes three injection seams that make it cheap to test
without hitting Postgres or Anthropic in the hot loop:

* ``runner`` — swap the real Hermes ``live_summary`` shim for a stub.
* ``status_reader`` — swap the DB status check for an in-memory dict
  lookup, so a 50ms tick does NOT pay a Postgres round-trip per tick
  (the test Postgres is on RunPod and easily exceeds 100ms RTT).
* ``persister`` — record summaries into a dict instead of writing them
  to the live DB.

These tests verify:

1. ``start_for`` registers the meeting; ``stop_for`` cancels and
   unregisters it.
2. The loop calls the runner, persists the resulting summary, and bails
   when the meeting is no longer ``status='live'``.
3. The route layer wires both lifecycle hooks so a ``POST /api/live-meetings``
   plus a follow-up ``/end`` produces a started-then-stopped task.
4. ``GET /api/live-meetings/{id}/summary`` and the ``live_summary`` field
   on the segments response surface whatever the loop persisted.
"""
from __future__ import annotations

import asyncio

import pytest

from storage_router import live_extraction
from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow


# ---------------------------------------------------------------------------
# Fixtures + helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_tasks():
    """Defensive cleanup so a leaked task from one test cannot pollute another."""
    live_extraction._TASKS.clear()
    yield
    for mid in list(live_extraction._TASKS):
        live_extraction.stop_for(mid)


class _InMemoryWorld:
    """Backing store for the in-memory status + persister seams."""

    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.summary: dict[str, str] = {}

    def reader(self, meeting_id: str) -> str | None:
        return self.status.get(meeting_id)

    def persister(self, meeting_id: str, summary: str) -> None:
        # Mirror real semantics: empty summary does NOT overwrite.
        if not summary:
            return
        self.summary[meeting_id] = summary


def _read_summary_db(meeting_id: str) -> str | None:
    session = SessionLocal()
    try:
        meeting = session.get(MeetingRow, meeting_id)
        return None if meeting is None else meeting.live_summary
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Loop unit tests (no FastAPI)
# ---------------------------------------------------------------------------


async def test_loop_persists_summary_each_tick():
    world = _InMemoryWorld()
    meeting_id = "m_persist_tick"
    world.status[meeting_id] = "live"
    calls: list[str] = []

    def runner(mid: str) -> dict:
        calls.append(mid)
        return {"summary": f"tick #{len(calls)}", "iterations": 1}

    task = live_extraction.start_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        persister=world.persister,
    )
    assert task is not None
    # Wait long enough for ~3 ticks (sleep-first loop; all hot-path
    # calls are pure-Python — no network in the seam).
    await asyncio.sleep(0.1)
    live_extraction.stop_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 2, calls
    assert all(c == meeting_id for c in calls)
    summary = world.summary.get(meeting_id)
    assert summary is not None
    assert summary.startswith("tick #")


async def test_loop_exits_when_meeting_no_longer_live():
    world = _InMemoryWorld()
    meeting_id = "m_exit_on_status"
    world.status[meeting_id] = "live"
    calls: list[str] = []

    def runner(mid: str) -> dict:
        calls.append(mid)
        return {"summary": "should not see many of these", "iterations": 1}

    task = live_extraction.start_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        persister=world.persister,
    )
    assert task is not None
    # Flip status before the first tick fires.
    world.status[meeting_id] = "ready"
    await asyncio.sleep(0.1)
    # Loop should have exited cleanly (not via cancel).
    assert task.done()
    assert task.exception() is None
    assert calls == []


async def test_runner_exception_does_not_kill_loop():
    world = _InMemoryWorld()
    meeting_id = "m_runner_oops"
    world.status[meeting_id] = "live"
    state = {"calls": 0}

    def runner(mid: str) -> dict:
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("simulated LLM 500")
        return {"summary": "recovered", "iterations": 1}

    task = live_extraction.start_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        persister=world.persister,
    )
    assert task is not None
    await asyncio.sleep(0.1)
    live_extraction.stop_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state["calls"] >= 2
    assert world.summary.get(meeting_id) == "recovered"


async def test_empty_summary_does_not_overwrite_prior():
    world = _InMemoryWorld()
    meeting_id = "m_no_overwrite"
    world.status[meeting_id] = "live"
    state = {"calls": 0}

    def runner(mid: str) -> dict:
        state["calls"] += 1
        if state["calls"] == 1:
            return {"summary": "first good summary", "iterations": 1}
        return {"summary": "", "iterations": 1}

    task = live_extraction.start_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        persister=world.persister,
    )
    await asyncio.sleep(0.1)
    live_extraction.stop_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    # Despite later empty summaries, the dict keeps the first-good value.
    assert world.summary.get(meeting_id) == "first good summary"


def test_start_for_no_event_loop_returns_none():
    """If no event loop is running we no-op rather than crash.

    The synchronous ``TestClient`` path used by some downstream callers
    never has a loop; the production Uvicorn path always does.
    """
    task = live_extraction.start_for("m_no_loop")
    assert task is None
    assert not live_extraction.is_running("m_no_loop")


def test_stop_for_unknown_is_noop():
    # No exception should escape.
    live_extraction.stop_for("m_never_started")


# ---------------------------------------------------------------------------
# Route-level wiring (uses the existing httpx async client fixture)
# ---------------------------------------------------------------------------


async def test_post_live_meetings_starts_summary_loop(client, monkeypatch):
    """Creating a live meeting installs a task in the global registry."""
    # Swap the runner so we never call Anthropic.
    monkeypatch.setattr(
        live_extraction,
        "_default_summary_runner",
        lambda meeting_id: {"summary": "stub", "iterations": 1},
    )
    resp = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "wired"},
    )
    assert resp.status_code == 201
    meeting_id = resp.json()["meeting_id"]
    assert live_extraction.is_running(meeting_id)
    # End cleanly so the autouse fixture sees an empty registry.
    end = await client.post(f"/api/live-meetings/{meeting_id}/end")
    assert end.status_code == 200
    # /end should have called stop_for; the meeting is no longer registered.
    assert not live_extraction.is_running(meeting_id)


async def test_summary_endpoint_returns_persisted_value(client, monkeypatch):
    monkeypatch.setattr(
        live_extraction,
        "_default_summary_runner",
        lambda meeting_id: {"summary": "irrelevant", "iterations": 1},
    )
    resp = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "summary read"},
    )
    meeting_id = resp.json()["meeting_id"]

    # No tick has fired yet -> summary is None.
    initial = await client.get(f"/api/live-meetings/{meeting_id}/summary")
    assert initial.status_code == 200
    body = initial.json()
    assert body == {"meeting_id": meeting_id, "status": "live", "summary": None}

    # Simulate a tick result by writing directly.
    live_extraction._persist_summary(meeting_id, "rolling-summary-text")
    after = (await client.get(f"/api/live-meetings/{meeting_id}/summary")).json()
    assert after["summary"] == "rolling-summary-text"

    # Same value also bundled into the segments response.
    segs = (await client.get(f"/api/live-meetings/{meeting_id}/segments")).json()
    assert segs["live_summary"] == "rolling-summary-text"
    await client.post(f"/api/live-meetings/{meeting_id}/end")


async def test_summary_endpoint_404_unknown_meeting(client):
    resp = await client.get("/api/live-meetings/m_does_not_exist/summary")
    assert resp.status_code == 404
