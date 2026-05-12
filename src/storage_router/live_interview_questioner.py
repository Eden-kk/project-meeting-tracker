"""Live interview questioner — per-meeting tick loop (Q1 slice).

Started by `live_route.create_live_meeting` (only when `interviewee_name IS
NOT NULL`) and cancelled by `live_route.end_live_meeting`. Every
`QUESTIONER_TICK_SECONDS` (default 60 s) the loop reads the last
`QUESTIONER_WINDOW_SECONDS` of finalized sentence text, passes it together
with the interviewee name and role to the `live-interview-questioner` skill,
and overwrites `meetings.suggested_questions` with the returned list (capped
at 5). When `interviewee_name` is NULL the loop is never started, so regular
meetings incur zero LLM cost.

Pattern: mirrors `storage_router/live_topic_tracker.py` line-for-line.
Tasks live in `app.state.live_tasks[meeting_id]["questioner"]`.
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy.orm import Session

from storage_router.db import SessionLocal
from storage_router.models.db import MeetingRow

logger = logging.getLogger(__name__)

QUESTIONER_TICK_SECONDS = int(os.environ.get("QUESTIONER_TICK_SECONDS", "60"))
QUESTIONER_WINDOW_SECONDS = int(os.environ.get("QUESTIONER_WINDOW_SECONDS", "180"))


def _build_snippet(session: Session, meeting_id: str) -> tuple[str, str | None, str | None]:
    """Return (transcript_snippet, interviewee_name, interviewee_role)."""
    from storage_router import storage  # local import; module-level cycle

    row = session.get(MeetingRow, meeting_id)
    if row is None:
        return "", None, None
    interviewee_name = row.interviewee_name
    interviewee_role = row.interviewee_role

    transcript = storage.get_transcript(session, meeting_id)
    if transcript is None:
        return "", interviewee_name, interviewee_role
    segments = list(transcript.segments)
    if not segments:
        return "", interviewee_name, interviewee_role
    cutoff_ms = max(0, (segments[-1].end_ms or 0) - QUESTIONER_WINDOW_SECONDS * 1000)
    tail = [s for s in segments if (s.end_ms or 0) >= cutoff_ms]
    snippet = " ".join(s.text for s in tail if s.text)
    return snippet, interviewee_name, interviewee_role


def _persist_questions(meeting_id: str, questions: list[str]) -> None:
    with SessionLocal() as session:
        row = session.get(MeetingRow, meeting_id)
        if row is None:
            return
        # race-mitigation: drop stale writes if meeting ended mid-LLM-call
        if row.status != "live":
            return
        row.suggested_questions = questions[:5]
        session.commit()


async def questioner_loop(
    meeting_id: str,
    *,
    tick_seconds: int = QUESTIONER_TICK_SECONDS,
    sleep: callable = asyncio.sleep,
) -> None:
    """Run the interview-questioner tick loop for one meeting until cancelled.

    Cancellation is the normal termination path (called by
    `end_live_meeting`); we swallow `asyncio.CancelledError` and let
    the task exit cleanly.
    """
    try:
        while True:
            try:
                with SessionLocal() as session:
                    snippet, name, role = _build_snippet(session, meeting_id)
                if snippet and name:
                    import hermes_plugin
                    output = await asyncio.to_thread(
                        hermes_plugin.live_interview_questions,
                        meeting_id, name, role, snippet,
                    )
                    _persist_questions(meeting_id, output.get("questions", []))
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "questioner_loop: meeting=%s tick failed: %s", meeting_id, exc
                )
            await sleep(tick_seconds)
    except asyncio.CancelledError:
        logger.info("questioner_loop: meeting=%s cancelled", meeting_id)
        raise


def start_questioner_loop(app, meeting_id: str) -> None:
    """Spawn the per-meeting questioner loop and register it on app.state.

    Idempotent: if a task is already registered for this meeting, do
    nothing. Gate: reads `interviewee_name` from the DB; skips the loop
    when NULL (regular meetings must not pay LLM cost).
    Stored under `app.state.live_tasks[meeting_id]["questioner"]`.
    """
    with SessionLocal() as session:
        row = session.get(MeetingRow, meeting_id)
        if row is None or row.interviewee_name is None:
            return

    tasks: dict = app.state.live_tasks
    bucket = tasks.setdefault(meeting_id, {})
    if "questioner" in bucket and not bucket["questioner"].done():
        return
    bucket["questioner"] = asyncio.create_task(
        questioner_loop(meeting_id),
        name=f"live-interview-questioner:{meeting_id}",
    )


def cancel_questioner_loop(app, meeting_id: str) -> None:
    """Cancel + drop the per-meeting questioner loop. Idempotent."""
    tasks: dict = app.state.live_tasks
    bucket = tasks.get(meeting_id)
    if not bucket:
        return
    task = bucket.pop("questioner", None)
    if task is not None and not task.done():
        task.cancel()


__all__ = [
    "QUESTIONER_TICK_SECONDS",
    "QUESTIONER_WINDOW_SECONDS",
    "cancel_questioner_loop",
    "questioner_loop",
    "start_questioner_loop",
]
