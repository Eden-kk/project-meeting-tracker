"""Wave 6.3 — periodic agent loop running ALONGSIDE live capture.

While the STT path appends transcript chunks every ~10s, this scheduler
fires on a longer cadence (~120s) and drives the
``live-meeting-summary`` Hermes skill over the transcript-so-far. The
skill returns a 3-5 sentence rolling summary which we persist in-place
to ``meetings.live_summary``; the frontend polls for it.

Wave 6.4 layers a second scheduler tick on top of this module that runs
``live-meeting-extraction`` over the SINCE-marked transcript window
``[last_live_extraction_end_ms - overlap_ms, now]`` and creates draft
cards. That tick is added in 6.4; the scaffolding (single ``_TASKS``
dict, ``start_for`` / ``stop_for``) is shared with both ticks so the
caller wires the lifecycle once.

Design choices
--------------

* **asyncio, not APScheduler.** The storage-router runs in a single
  Uvicorn worker for the MVP. Adding APScheduler would buy us nothing
  and would complicate test teardown. We use a plain
  ``asyncio.create_task`` per live meeting, stored on a
  process-local dict keyed by ``meeting_id``, cancelled at /end.
* **No DB session held across the sleep.** The loop opens a fresh
  ``SessionLocal`` on every tick so a 2-minute sleep cannot pin a
  Postgres connection. The Hermes skill itself uses
  :class:`StorageRouterClient` (HTTP), not a SQLAlchemy session.
* **Best-effort, never fail the request thread.** Any exception inside
  the loop is logged and swallowed. The next tick will retry with
  the latest transcript snapshot.
* **Status guard.** Before calling the LLM, the loop reads the
  current ``meetings.status`` and bails if it's no longer ``live``
  (the user may have ended the meeting between sleep ticks; the
  cancellation from ``stop_for`` covers the common case but a
  status check is a cheap belt-and-suspenders).
* **Test hooks.** Tests pass a small ``interval_s`` (e.g. 0.05) so
  the loop runs many ticks per second. Tests can also pass an
  injected ``runner`` callable to swap out the real Hermes call for
  a recorded stub.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Awaitable, Callable, Optional

from sqlalchemy.orm import Session

from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow

logger = logging.getLogger(__name__)


# Public knobs. Cadence is the time between two summary ticks; the
# extraction tick (Wave 6.4) uses the same cadence by default but can
# be overridden independently.
SUMMARY_INTERVAL_S = float(os.environ.get("LIVE_SUMMARY_INTERVAL_S", "120"))


# Keyed by meeting_id. Each value is the asyncio.Task driving the loop.
# Tests can inspect this dict to verify start/stop wiring.
_TASKS: dict[str, asyncio.Task] = {}


# Type aliases for the injection seams used by tests.
SummaryRunner = Callable[[str], dict]  # meeting_id -> {summary, iterations}
StatusReader = Callable[[str], Optional[str]]  # meeting_id -> "live" / "ready" / None
SummaryPersister = Callable[[str, str], None]  # meeting_id, summary -> None


def _meeting_status(meeting_id: str, session: Optional[Session] = None) -> Optional[str]:
    """Return the current ``meetings.status`` or None if the row is gone.

    A short-lived session is opened per call when one is not supplied so
    we never hold a Postgres connection across an ``asyncio.sleep``.
    """
    own_session = False
    if session is None:
        session = SessionLocal()
        own_session = True
    try:
        meeting = session.get(MeetingRow, meeting_id)
        return meeting.status if meeting is not None else None
    finally:
        if own_session:
            session.close()


def _persist_summary(meeting_id: str, summary: str) -> None:
    """Write the rolling summary back to ``meetings.live_summary``.

    Empty strings are treated as a no-op (the skill returned nothing
    useful — keep the prior snapshot rather than blank it out).
    """
    if not summary:
        return
    session = SessionLocal()
    try:
        meeting = session.get(MeetingRow, meeting_id)
        if meeting is None:
            return
        meeting.live_summary = summary
        session.commit()
    finally:
        session.close()


def _default_summary_runner(meeting_id: str) -> dict:
    """Default runner: dispatch to the Hermes plugin live_summary shim.

    Imported lazily so unit tests that never trigger a tick don't have
    to install ``anthropic``.
    """
    from hermes_plugin import live_summary as _live_summary

    return _live_summary(meeting_id)


async def _summary_loop(
    meeting_id: str,
    *,
    interval_s: float,
    runner: SummaryRunner,
    status_reader: StatusReader,
    persister: SummaryPersister,
) -> None:
    """Tick body for the rolling summary loop.

    Sleeps first so we don't fire immediately on meeting creation
    (the transcript would be empty). Each tick re-checks status and
    bails if the meeting has flipped out of ``live``.
    """
    try:
        while True:
            await asyncio.sleep(interval_s)
            status = await asyncio.to_thread(status_reader, meeting_id)
            if status != "live":
                logger.info(
                    "live_summary.loop_exit meeting=%s status=%s",
                    meeting_id,
                    status,
                )
                return
            try:
                result = await asyncio.to_thread(runner, meeting_id)
            except Exception as exc:  # noqa: BLE001 — best-effort tick
                logger.warning(
                    "live_summary.tick_failed meeting=%s err=%s",
                    meeting_id,
                    exc,
                )
                continue
            summary = (result or {}).get("summary", "") if isinstance(result, dict) else ""
            await asyncio.to_thread(persister, meeting_id, summary)
    except asyncio.CancelledError:
        # Normal shutdown path triggered by stop_for(); re-raise so the
        # task records as cancelled.
        raise


def start_for(
    meeting_id: str,
    *,
    interval_s: float = SUMMARY_INTERVAL_S,
    runner: Optional[SummaryRunner] = None,
    status_reader: Optional[StatusReader] = None,
    persister: Optional[SummaryPersister] = None,
) -> Optional[asyncio.Task]:
    """Spawn the summary loop for a freshly created live meeting.

    Returns the ``asyncio.Task`` for callers / tests that want to
    await it. If there is no running event loop (tests calling the
    route synchronously without an async client), this is a no-op
    and returns ``None`` — the production path always has a loop
    because FastAPI runs on Uvicorn.

    Tests can swap any of the three injection seams (``runner``,
    ``status_reader``, ``persister``) to avoid hitting Postgres /
    Anthropic in the hot loop.
    """
    if meeting_id in _TASKS:
        return _TASKS[meeting_id]
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return None
    runner = runner if runner is not None else _default_summary_runner
    status_reader = status_reader if status_reader is not None else _meeting_status
    persister = persister if persister is not None else _persist_summary
    task = loop.create_task(
        _summary_loop(
            meeting_id,
            interval_s=interval_s,
            runner=runner,
            status_reader=status_reader,
            persister=persister,
        ),
        name=f"live-summary:{meeting_id}",
    )
    _TASKS[meeting_id] = task
    return task


def stop_for(meeting_id: str) -> None:
    """Cancel and unregister the summary loop for ``meeting_id``.

    Safe to call multiple times — a missing task is a silent no-op.
    """
    task = _TASKS.pop(meeting_id, None)
    if task is None:
        return
    task.cancel()


def is_running(meeting_id: str) -> bool:
    """Test helper: did ``start_for`` install a task for this meeting?"""
    return meeting_id in _TASKS


__all__ = [
    "SUMMARY_INTERVAL_S",
    "start_for",
    "stop_for",
    "is_running",
]
