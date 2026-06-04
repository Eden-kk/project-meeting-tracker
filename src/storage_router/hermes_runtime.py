"""Lazy resolver for the in-process `hermes_plugin` package.

The Phase-2 default is to import Hermes directly. If the plugin is not
installed in the current venv (worktree F has not landed yet), the resolver
raises HermesUnavailable so the route can map it to a 503.

Phase-3 auto-finalize: this module also owns the
``auto_finalize_meeting(meeting_id)`` background-task entry. It opens
its own Session (FastAPI BackgroundTasks run after the request session
has closed), drives the meeting through ``ready → finalizing → finalized``
(or back to ``ready`` on failure with ``last_finalize_error`` set), and
uses an in-process semaphore to cap concurrent finalize calls at 2 — a
cheap guard against the Anthropic rate-limit blast radius described in
plans/misty-seeking-lantern.md (Risks section).
"""
from __future__ import annotations

import logging
import threading
from datetime import UTC, datetime

# threading.BoundedSemaphore works for both sync and async callers:
# Starlette's BackgroundTasks runs a non-async callable in a worker
# thread, so a thread-aware primitive is the right shape here.
_FINALIZE_CONCURRENCY = 2
_finalize_semaphore = threading.BoundedSemaphore(_FINALIZE_CONCURRENCY)

log = logging.getLogger(__name__)


class HermesUnavailable(RuntimeError):
    """Raised when hermes_plugin is missing or its expected entrypoint is absent."""


def _import_or_503():
    try:
        import hermes_plugin  # type: ignore[import-not-found]
    except ImportError as e:
        raise HermesUnavailable(str(e)) from None
    return hermes_plugin


def run_meeting_finalization(meeting_id: str, chunk_minutes: int = 5) -> dict:
    """Forward to ``hermes_plugin.meeting_finalization`` with the chunk knob.

    ``chunk_minutes`` is the time-window size (in minutes) used when the
    transcript carries timestamps. The plugin falls back to single-pass
    finalization for untimestamped transcripts regardless of this value.
    """
    mod = _import_or_503()
    fn = getattr(mod, "meeting_finalization", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.meeting_finalization not exported")
    return fn(meeting_id=meeting_id, chunk_minutes=chunk_minutes)


def run_meeting_qa(meeting_id: str, question: str) -> dict:
    mod = _import_or_503()
    fn = getattr(mod, "meeting_qa", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.meeting_qa not exported")
    return fn(meeting_id=meeting_id, question=question)


def run_followup_draft(
    meeting_id: str,
    recipient: str | None = None,
    tone: str | None = None,
) -> dict:
    """Wave 5.3 — forward to ``hermes_plugin.followup_draft``.

    Validation of ``recipient`` (sanitized, max 100 chars) and ``tone``
    happens in the route layer; this shim is intentionally thin so the
    plugin call can be mocked at the same boundary the other run_*
    helpers use.
    """
    mod = _import_or_503()
    fn = getattr(mod, "followup_draft", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.followup_draft not exported")
    return fn(meeting_id=meeting_id, recipient=recipient, tone=tone)


def run_project_orchestrator(question: str) -> dict:
    """Per-project orchestrator entry. The orchestrator decides which
    project subagent(s) to dispatch and synthesizes one user-facing
    answer with citations in ``[project:<ws>:meeting:<m>:card:<c>]``
    form. See ``hermes_plugin.orchestrator`` for the architecture.
    """
    mod = _import_or_503()
    fn = getattr(mod, "project_orchestrator", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.project_orchestrator not exported")
    return fn(question=question)


def run_workspace_qa(workspace_id: str, question: str) -> dict:
    """Wave 4.3: workspace-wide Hermes QA.

    Forwards to ``hermes_plugin.workspace_qa`` which is bound to the two
    cross-meeting search tools (`search_workspace_transcripts` and
    `search_workspace_cards`). Citations come back as
    ``[meeting:<id>:card:<id>]`` or ``[meeting:<id>:seg:<id>]`` so the
    SPA can deep-link to the source meeting.
    """
    mod = _import_or_503()
    fn = getattr(mod, "workspace_qa", None)
    if fn is None:
        raise HermesUnavailable("hermes_plugin.workspace_qa not exported")
    return fn(workspace_id=workspace_id, question=question)


def auto_finalize_meeting(meeting_id: str) -> None:
    """Background-task entry: drive ``ready → finalizing → finalized``.

    Opens its own Session (the request-scoped one is gone by the time
    this runs). Persists every card the plugin returns. On failure the
    meeting status reverts to ``ready`` and ``last_finalize_error`` is
    populated; the caller never sees an exception bubble up — this is
    fire-and-forget per FastAPI BackgroundTasks contract.
    """
    # Cheap rate-limit mitigation. If we cannot acquire within ~30s the
    # task aborts and leaves status at `ready` so the next manual or
    # auto trigger can have another go.
    acquired = _finalize_semaphore.acquire(timeout=30.0)
    if not acquired:
        log.warning(
            "auto_finalize_meeting: timed out waiting for finalize slot (meeting=%s)",
            meeting_id,
        )
        return
    try:
        _finalize_inner(meeting_id)
    finally:
        _finalize_semaphore.release()


def _finalize_inner(meeting_id: str) -> None:
    """The transactional body of auto_finalize_meeting, factored out so
    tests can monkeypatch the runtime call site cleanly."""
    # Local imports avoid a circular import at module load time.
    from sqlalchemy import select

    from storage_router import storage
    from storage_router.db import SessionLocal
    from storage_router.models.db import (
        ConversationArtifactRow,
        MeetingRow,
        Workspace,
    )
    from storage_router.models.memory_cards import MemoryCardCreate

    with SessionLocal() as session:
        meeting = session.execute(
            select(MeetingRow).where(MeetingRow.id == meeting_id).with_for_update()
        ).scalar_one_or_none()
        if meeting is None:
            log.warning("auto_finalize_meeting: meeting %s missing", meeting_id)
            return
        if meeting.status != "ready":
            log.info(
                "auto_finalize_meeting: skipping meeting=%s (status=%s, expected ready)",
                meeting_id,
                meeting.status,
            )
            return
        meeting.status = "finalizing"
        # Clear any prior error from a previous attempt.
        meeting.last_finalize_error = None
        session.commit()

    try:
        result = run_meeting_finalization(meeting_id)
    except Exception as exc:  # noqa: BLE001 — fire-and-forget surface.
        log.exception(
            "auto_finalize_meeting: hermes call failed (meeting=%s)", meeting_id
        )
        with SessionLocal() as session:
            meeting = session.get(MeetingRow, meeting_id)
            if meeting is not None:
                meeting.status = "ready"
                meeting.last_finalize_error = str(exc)[:1000]
                session.commit()
        return

    try:
        with SessionLocal() as session:
            meeting = session.execute(
                select(MeetingRow).where(MeetingRow.id == meeting_id).with_for_update()
            ).scalar_one()

            cards_in = [MemoryCardCreate(**c) for c in result.get("cards", [])]
            for card in cards_in:
                storage.create_memory_card(
                    session,
                    meeting_id=meeting_id,
                    type=card.type.value,
                    title=card.title,
                    content=card.content,
                    source_chunk_ids=card.source_chunk_ids,
                    confidence=card.confidence,
                    source_start_ms=card.source_start_ms,
                    source_end_ms=card.source_end_ms,
                    speakers_json=card.speakers_json,
                    created_by_agent=card.created_by_agent,
                )

            # Persist the finalize-skill summary so the SPA's Summary tab
            # can render it without re-invoking the LLM. Stored even if the
            # skill returned an empty string — caller can distinguish "no
            # summary yet" (NULL) from "summary was empty" (empty string).
            summary = result.get("summary")
            if isinstance(summary, str):
                meeting.finalized_summary = summary
            meeting.status = "finalized"
            meeting.finalized_at = datetime.now(UTC)
            meeting.last_finalize_error = None

            # Denormalize meetings.finalized_at onto workspaces.last_meeting_at
            # for the orchestrator's freshness heuristic. Best-effort: a miss
            # here only delays a newly-finalized meeting from showing up in
            # the orchestrator's fan-out criteria by one cache cycle.
            artifact = session.get(
                ConversationArtifactRow, meeting.artifact_id
            )
            if artifact is not None:
                workspace = session.get(Workspace, artifact.workspace_id)
                if workspace is not None:
                    workspace.last_meeting_at = meeting.finalized_at

            session.commit()
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "auto_finalize_meeting: persistence failed (meeting=%s)", meeting_id
        )
        with SessionLocal() as session:
            meeting = session.get(MeetingRow, meeting_id)
            if meeting is not None:
                meeting.status = "ready"
                meeting.last_finalize_error = f"persist_failed: {exc}"[:1000]
                session.commit()


def finalize_live_meeting(meeting_id: str) -> None:
    """Background-task entry: finalize a live meeting on /end.

    Live meetings accumulate draft cards during the meeting via the
    live-extraction loop, so — unlike the batch path — we must NOT re-run
    extraction here (it would duplicate those cards). Instead we generate
    the narrative summary from the transcript and mark the meeting
    finalized. Status flows ``ready → finalizing → finalized`` (revert to
    ``ready`` with ``last_finalize_error`` on failure). Fire-and-forget per
    the FastAPI BackgroundTasks contract — never raises to the caller.
    """
    acquired = _finalize_semaphore.acquire(timeout=30.0)
    if not acquired:
        log.warning(
            "finalize_live_meeting: timed out waiting for finalize slot (meeting=%s)",
            meeting_id,
        )
        return
    try:
        _finalize_live_inner(meeting_id)
    except Exception:  # noqa: BLE001 — fire-and-forget; never raise to caller.
        log.exception(
            "finalize_live_meeting: unexpected error (meeting=%s)", meeting_id
        )
    finally:
        _finalize_semaphore.release()


def _finalize_live_inner(meeting_id: str) -> None:
    from sqlalchemy import select

    from storage_router.db import SessionLocal
    from storage_router.models.db import (
        ConversationArtifactRow,
        MeetingRow,
        Workspace,
    )

    with SessionLocal() as session:
        meeting = session.execute(
            select(MeetingRow).where(MeetingRow.id == meeting_id).with_for_update()
        ).scalar_one_or_none()
        if meeting is None:
            log.warning("finalize_live_meeting: meeting %s missing", meeting_id)
            return
        if meeting.status != "ready":
            log.info(
                "finalize_live_meeting: skipping meeting=%s (status=%s, expected ready)",
                meeting_id,
                meeting.status,
            )
            return
        meeting.status = "finalizing"
        meeting.last_finalize_error = None
        session.commit()

    try:
        hermes = _import_or_503()
        summarize = getattr(hermes, "summarize_meeting", None)
        if summarize is None:
            raise HermesUnavailable("hermes_plugin.summarize_meeting not exported")
        summary = summarize(meeting_id)
    except Exception as exc:  # noqa: BLE001 — fire-and-forget surface.
        log.exception(
            "finalize_live_meeting: summary failed (meeting=%s)", meeting_id
        )
        with SessionLocal() as session:
            meeting = session.get(MeetingRow, meeting_id)
            if meeting is not None:
                meeting.status = "ready"
                meeting.last_finalize_error = str(exc)[:1000]
                session.commit()
        return

    try:
        with SessionLocal() as session:
            meeting = session.execute(
                select(MeetingRow).where(MeetingRow.id == meeting_id).with_for_update()
            ).scalar_one()
            if isinstance(summary, str):
                meeting.finalized_summary = summary
            meeting.status = "finalized"
            meeting.finalized_at = datetime.now(UTC)
            meeting.last_finalize_error = None
            artifact = session.get(ConversationArtifactRow, meeting.artifact_id)
            if artifact is not None:
                workspace = session.get(Workspace, artifact.workspace_id)
                if workspace is not None:
                    workspace.last_meeting_at = meeting.finalized_at
            session.commit()
    except Exception as exc:  # noqa: BLE001
        log.exception(
            "finalize_live_meeting: persistence failed (meeting=%s)", meeting_id
        )
        with SessionLocal() as session:
            meeting = session.get(MeetingRow, meeting_id)
            if meeting is not None:
                meeting.status = "ready"
                meeting.last_finalize_error = f"persist_failed: {exc}"[:1000]
                session.commit()
