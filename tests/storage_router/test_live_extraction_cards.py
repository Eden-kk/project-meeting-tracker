"""Tests for the Wave 6.4 periodic draft-card extraction tick.

The extraction loop sits next to the summary loop (6.3) and uses the
same injection-seam pattern: ``runner``, ``status_reader``,
``watermark_reader``, ``watermark_writer``. None of the seams hit
Postgres or Anthropic, so a 50ms tick is comfortable in tests.

Verifies:

1. The loop calls the runner with the watermark value and advances the
   watermark to the returned ``window_end_ms``.
2. A failing runner does NOT advance the watermark — the next tick
   retries from the same window.
3. A returned ``window_end_ms`` that's <= the prior watermark is
   ignored (no rollback).
4. ``stop_extraction_for`` cancels the loop cleanly; ``stop_for``
   does NOT cancel the extraction loop (independent registries).
5. Route-level wiring: ``POST /api/live-meetings`` starts BOTH loops;
   ``POST /.../end`` stops BOTH.
6. ``GET /api/live-meetings/{id}/draft-cards`` returns visible cards
   in creation order with optional ``since_iso`` filter.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from storage_router import live_extraction, storage
from storage_router.db import SessionLocal


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _clear_extraction_tasks():
    live_extraction._TASKS.clear()
    live_extraction._EXTRACTION_TASKS.clear()
    yield
    for mid in list(live_extraction._TASKS):
        live_extraction.stop_for(mid)
    for mid in list(live_extraction._EXTRACTION_TASKS):
        live_extraction.stop_extraction_for(mid)


class _ExtractionWorld:
    """In-memory backing for the extraction loop seams."""

    def __init__(self, *, status: str = "live") -> None:
        self.status: dict[str, str] = {}
        self.watermark: dict[str, int] = {}
        self._default_status = status

    def reader(self, meeting_id: str) -> str | None:
        return self.status.get(meeting_id, self._default_status)

    def watermark_get(self, meeting_id: str) -> int | None:
        return self.watermark.get(meeting_id)

    def watermark_set(self, meeting_id: str, end_ms: int) -> None:
        prior = self.watermark.get(meeting_id)
        if prior is not None and end_ms <= prior:
            return
        self.watermark[meeting_id] = end_ms


# ---------------------------------------------------------------------------
# Loop unit tests
# ---------------------------------------------------------------------------


async def test_extraction_loop_advances_watermark():
    world = _ExtractionWorld()
    meeting_id = "m_extract_advance"
    world.status[meeting_id] = "live"
    calls: list[tuple[str, int | None]] = []

    def runner(mid: str, since_ms: int | None) -> dict:
        calls.append((mid, since_ms))
        return {
            "cards_created": 1,
            "window_start_ms": (since_ms or 0),
            "window_end_ms": (since_ms or 0) + 60_000,
            "summary": "ok",
            "iterations": 1,
        }

    task = live_extraction.start_extraction_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        watermark_reader=world.watermark_get,
        watermark_writer=world.watermark_set,
    )
    assert task is not None
    await asyncio.sleep(0.1)
    live_extraction.stop_extraction_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 2
    # First call: since_ms None (unset). Subsequent calls see the
    # watermark we set on the prior tick.
    assert calls[0][1] is None
    assert calls[1][1] == 60_000  # the watermark advanced by one window
    assert world.watermark[meeting_id] >= 60_000


async def test_runner_failure_does_not_advance_watermark():
    world = _ExtractionWorld()
    meeting_id = "m_extract_retry"
    world.status[meeting_id] = "live"
    world.watermark[meeting_id] = 30_000
    state = {"calls": 0}

    def runner(mid: str, since_ms: int | None) -> dict:
        state["calls"] += 1
        if state["calls"] == 1:
            raise RuntimeError("simulated extraction 500")
        return {
            "cards_created": 0,
            "window_start_ms": since_ms or 0,
            "window_end_ms": (since_ms or 0) + 30_000,
            "summary": "",
            "iterations": 1,
        }

    task = live_extraction.start_extraction_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        watermark_reader=world.watermark_get,
        watermark_writer=world.watermark_set,
    )
    await asyncio.sleep(0.1)
    live_extraction.stop_extraction_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    assert state["calls"] >= 2
    # First failed (no advance); subsequent ticks succeeded and the
    # watermark moved monotonically forward from the seeded 30_000.
    assert world.watermark[meeting_id] >= 60_000
    assert world.watermark[meeting_id] > 30_000


async def test_extraction_loop_ignores_backwards_window_end():
    world = _ExtractionWorld()
    meeting_id = "m_no_rewind"
    world.status[meeting_id] = "live"
    world.watermark[meeting_id] = 100_000
    state = {"calls": 0}

    def runner(mid: str, since_ms: int | None) -> dict:
        state["calls"] += 1
        # Pretend the model returned an older window_end (clock skew).
        return {
            "cards_created": 0,
            "window_start_ms": 50_000,
            "window_end_ms": 50_000,
            "summary": "",
            "iterations": 1,
        }

    task = live_extraction.start_extraction_for(
        meeting_id,
        interval_s=0.02,
        runner=runner,
        status_reader=world.reader,
        watermark_reader=world.watermark_get,
        watermark_writer=world.watermark_set,
    )
    await asyncio.sleep(0.07)
    live_extraction.stop_extraction_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await task
    # Watermark must NOT have rewound.
    assert world.watermark[meeting_id] == 100_000


async def test_stop_for_does_not_cancel_extraction():
    """The summary and extraction loops are independent — stopping one
    must NOT take down the other."""
    world = _ExtractionWorld()
    meeting_id = "m_independent"
    world.status[meeting_id] = "live"
    summary_calls: list[int] = []
    extraction_calls: list[int] = []

    def summary_runner(mid: str) -> dict:
        summary_calls.append(time.monotonic_ns())
        return {"summary": "s", "iterations": 1}

    def extraction_runner(mid: str, since_ms: int | None) -> dict:
        extraction_calls.append(time.monotonic_ns())
        return {
            "cards_created": 0,
            "window_start_ms": 0,
            "window_end_ms": 1_000,
            "summary": "",
            "iterations": 1,
        }

    summary_task = live_extraction.start_for(
        meeting_id,
        interval_s=0.02,
        runner=summary_runner,
        status_reader=world.reader,
        persister=lambda *_a: None,
    )
    extraction_task = live_extraction.start_extraction_for(
        meeting_id,
        interval_s=0.02,
        runner=extraction_runner,
        status_reader=world.reader,
        watermark_reader=world.watermark_get,
        watermark_writer=world.watermark_set,
    )
    await asyncio.sleep(0.06)
    # Stop ONLY the summary loop.
    live_extraction.stop_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await summary_task

    summary_count_after_stop = len(summary_calls)
    await asyncio.sleep(0.06)
    # Summary should not have advanced.
    assert len(summary_calls) == summary_count_after_stop
    # Extraction should have continued.
    assert len(extraction_calls) > 1
    assert live_extraction.is_extraction_running(meeting_id)
    live_extraction.stop_extraction_for(meeting_id)
    with pytest.raises(asyncio.CancelledError):
        await extraction_task


# ---------------------------------------------------------------------------
# Route-level wiring + draft-cards endpoint
# ---------------------------------------------------------------------------


async def test_create_route_starts_both_loops(client, monkeypatch):
    monkeypatch.setattr(
        live_extraction,
        "_default_summary_runner",
        lambda meeting_id: {"summary": "stub", "iterations": 1},
    )
    monkeypatch.setattr(
        live_extraction,
        "_default_extraction_runner",
        lambda meeting_id, since_ms: {
            "cards_created": 0,
            "window_start_ms": 0,
            "window_end_ms": 0,
            "summary": "",
            "iterations": 0,
        },
    )
    resp = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "both-loops"},
    )
    assert resp.status_code == 201
    meeting_id = resp.json()["meeting_id"]
    assert live_extraction.is_running(meeting_id)
    assert live_extraction.is_extraction_running(meeting_id)
    end = await client.post(f"/api/live-meetings/{meeting_id}/end")
    assert end.status_code == 200
    assert not live_extraction.is_running(meeting_id)
    assert not live_extraction.is_extraction_running(meeting_id)


async def test_draft_cards_endpoint_lists_and_filters_by_since(
    client, monkeypatch
):
    """End-to-end exercise: create a meeting, hand-create two cards,
    confirm both endpoints behaviours."""
    monkeypatch.setattr(
        live_extraction, "_default_summary_runner",
        lambda meeting_id: {"summary": "", "iterations": 0},
    )
    monkeypatch.setattr(
        live_extraction, "_default_extraction_runner",
        lambda meeting_id, since_ms: {
            "cards_created": 0,
            "window_start_ms": 0,
            "window_end_ms": 0,
            "summary": "",
            "iterations": 0,
        },
    )
    resp = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "draft-cards-endpoint"},
    )
    meeting_id = resp.json()["meeting_id"]

    # Create one card directly via storage.
    session = SessionLocal()
    try:
        first = storage.create_memory_card(
            session,
            meeting_id=meeting_id,
            type="decision",
            title="first-card",
            content="x",
            source_chunk_ids=["seg_1"],
            confidence=0.9,
            source_start_ms=0,
            source_end_ms=1000,
            speakers_json=["Alice"],
            created_by_agent="live-meeting-extraction",
        )
        session.commit()
        first_created_at = first.created_at
    finally:
        session.close()

    # No since filter -> see the one card.
    resp = await client.get(f"/api/live-meetings/{meeting_id}/draft-cards")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "live"
    assert len(body["items"]) == 1
    assert body["items"][0]["title"] == "first-card"

    # Add a second card.
    session = SessionLocal()
    try:
        storage.create_memory_card(
            session,
            meeting_id=meeting_id,
            type="action_item",
            title="second-card",
            content="y",
            source_chunk_ids=["seg_2"],
            confidence=0.7,
            source_start_ms=2000,
            source_end_ms=3000,
            speakers_json=["Bob"],
            created_by_agent="live-meeting-extraction",
        )
        session.commit()
    finally:
        session.close()

    # since_iso = first card's created_at -> only the second card.
    after = await client.get(
        f"/api/live-meetings/{meeting_id}/draft-cards",
        params={"since_iso": first_created_at.isoformat()},
    )
    assert after.status_code == 200
    items = after.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "second-card"

    await client.post(f"/api/live-meetings/{meeting_id}/end")


async def test_draft_cards_endpoint_404_unknown(client):
    resp = await client.get("/api/live-meetings/m_does_not_exist/draft-cards")
    assert resp.status_code == 404


async def test_draft_cards_endpoint_rejects_bad_since(client, monkeypatch):
    monkeypatch.setattr(
        live_extraction, "_default_summary_runner",
        lambda meeting_id: {"summary": "", "iterations": 0},
    )
    monkeypatch.setattr(
        live_extraction, "_default_extraction_runner",
        lambda meeting_id, since_ms: {
            "cards_created": 0,
            "window_start_ms": 0,
            "window_end_ms": 0,
            "summary": "",
            "iterations": 0,
        },
    )
    resp = await client.post(
        "/api/live-meetings",
        data={"workspace_id": "ws_dev", "title": "x"},
    )
    meeting_id = resp.json()["meeting_id"]
    bad = await client.get(
        f"/api/live-meetings/{meeting_id}/draft-cards",
        params={"since_iso": "not-a-date"},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"]["error"]["code"] == "bad_since"
    await client.post(f"/api/live-meetings/{meeting_id}/end")
