"""Wave 8.6 — per-meeting "currently discussing X" tick loop.

Started by `live_route.create_live_meeting` and cancelled by
`live_route.end_live_meeting`. Every `TOPIC_TICK_SECONDS` (default 30 s)
the loop pulls the last `TOPIC_WINDOW_SECONDS` of finalized sentence
text directly from storage (no Hermes `get_meeting_transcript` tool —
that 409s for status='live') and asks the `live-topic-tracker` skill
for a one-line topic. The skill refuses with the literal sentinel
`__TOPIC_INSUFFICIENT__` when there is too little content; we map that
to `current_topic = NULL` so the UI shows a "…" placeholder rather than
a hallucinated topic.

Pattern: matches the "Per-meeting task lifecycle" section of the plan.
Tasks live in `app.state.live_tasks: dict[str, asyncio.Task]`, keyed by
meeting_id with a sub-key for "topic" (so 8.5's gate consumer, if it
ever moves to a separate task, can co-exist on the same dict).
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.orm import Session

from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow

logger = logging.getLogger(__name__)

TOPIC_TICK_SECONDS = int(os.environ.get("TOPIC_TICK_SECONDS", "30"))
TOPIC_WINDOW_SECONDS = int(os.environ.get("TOPIC_WINDOW_SECONDS", "60"))
TOPIC_REFUSAL_SENTINEL = "__TOPIC_INSUFFICIENT__"


def _build_snippet(session: Session, meeting_id: str) -> str:
    """Return the last `TOPIC_WINDOW_SECONDS` of finalized sentence text.

    Uses the existing `storage.get_transcript(...)` API which handles
    speaker/timestamp shaping — we only need the raw text.
    """
    from storage_router import storage  # local import; module-level cycle

    transcript = storage.get_transcript(session, meeting_id)
    if transcript is None:
        return ""
    segments = list(transcript.segments)
    if not segments:
        return ""
    # Take rows whose end_ms falls inside the trailing window.
    cutoff_ms = max(0, (segments[-1].end_ms or 0) - TOPIC_WINDOW_SECONDS * 1000)
    tail = [s for s in segments if (s.end_ms or 0) >= cutoff_ms]
    return " ".join(s.text for s in tail if s.text)


def _call_skill(snippet: str) -> str | None:
    """Invoke the `live-topic-tracker` Hermes skill via the LLM dispatcher.

    Returns the model's raw single-line output, or None when the model
    refused with the sentinel. Lazy import so unit tests can patch
    `hermes_plugin.live_topic_tracker` without paying the LLM-SDK
    import cost up front.
    """
    import hermes_plugin

    raw = hermes_plugin.live_topic_tracker(snippet).strip()
    if raw == TOPIC_REFUSAL_SENTINEL or not raw:
        return None
    return raw


def _persist_topic(meeting_id: str, topic: str | None) -> None:
    """Open a fresh session and update `meetings.current_topic`."""
    with SessionLocal() as session:
        row = session.get(MeetingRow, meeting_id)
        if row is None:
            return  # meeting deleted between tick and write — no-op
        row.current_topic = topic
        session.commit()


async def topic_loop(
    meeting_id: str,
    *,
    tick_seconds: int = TOPIC_TICK_SECONDS,
    sleep: callable = asyncio.sleep,
) -> None:
    """Run the topic-tracker tick loop for one meeting until cancelled.

    Cancellation is the normal termination path (called by
    `end_live_meeting`); we swallow `asyncio.CancelledError` and let
    the task exit cleanly.
    """
    try:
        while True:
            try:
                with SessionLocal() as session:
                    snippet = _build_snippet(session, meeting_id)
                if snippet:
                    topic = await asyncio.to_thread(_call_skill, snippet)
                    _persist_topic(meeting_id, topic)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "topic_loop: meeting=%s tick failed: %s", meeting_id, exc
                )
            await sleep(tick_seconds)
    except asyncio.CancelledError:
        logger.info("topic_loop: meeting=%s cancelled", meeting_id)
        raise


def start_topic_loop(app, meeting_id: str) -> None:
    """Spawn the per-meeting topic loop and register it on app.state.

    Idempotent: if a task is already registered for this meeting, do
    nothing. Stored under `app.state.live_tasks[meeting_id]["topic"]`.
    """
    tasks: dict = app.state.live_tasks
    bucket = tasks.setdefault(meeting_id, {})
    if "topic" in bucket and not bucket["topic"].done():
        return
    bucket["topic"] = asyncio.create_task(
        topic_loop(meeting_id),
        name=f"live-topic-tracker:{meeting_id}",
    )


def cancel_topic_loop(app, meeting_id: str) -> None:
    """Cancel + drop the per-meeting topic loop. Idempotent."""
    tasks: dict = app.state.live_tasks
    bucket = tasks.pop(meeting_id, None)
    if not bucket:
        return
    task = bucket.get("topic")
    if task is not None and not task.done():
        task.cancel()


__all__ = [
    "TOPIC_REFUSAL_SENTINEL",
    "TOPIC_TICK_SECONDS",
    "TOPIC_WINDOW_SECONDS",
    "cancel_topic_loop",
    "start_topic_loop",
    "topic_loop",
]
