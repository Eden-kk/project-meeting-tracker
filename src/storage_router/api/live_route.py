"""Live capture routes — Phase 3 Wave 6.2 (real STT per chunk).

Browser-side `MediaRecorder` POSTs ~5s WebM chunks to this service. For each
chunk we:
  1. persist the blob to ``LIVE_CHUNK_DIR/<meeting>/<seq>.webm`` (so a human
     can replay/debug),
  2. hand the file to voice-ingest via
     ``ingest_adapter_http.transcribe_voice_file``,
  3. shift each returned segment's ``start_ms`` / ``end_ms`` by the running
     offset (sum of prior chunk durations) so the merged transcript reads as
     one continuous timeline,
  4. write the resulting ``speaker_segments`` rows.

If voice-ingest is unreachable we fall back to a placeholder row so the live
panel still moves; the row is tagged with ``confidence=0.0`` so callers can
filter it out later.

Routes:
    POST /api/live-meetings                                  -> create
    POST /api/live-meetings/{meeting_id}/audio-chunk         -> persist + transcribe
    POST /api/live-meetings/{meeting_id}/end                 -> flip status to ready
    GET  /api/live-meetings/{meeting_id}/segments[?since=]   -> poll transcript
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from storage_router import ingest_adapter_http, live_extraction, storage
from storage_router.db import get_session
from storage_router.ids import new_id
from storage_router.models.db import (
    MeetingRow,
    MeetingSourceRow,
    SpeakerSegmentRow,
)
from storage_router.sentence_buffer import (
    CompleteSentence,
    SentenceBuffer,
    WhisperSeg,
)

try:
    # Wave 8.3 default for the force-flush window. Falls back to the
    # SentenceBuffer module default if voice_ingest is not installed in
    # the same env (e.g. unit-test sandbox).
    from voice_ingest.config import PUNCT_MAX_WAIT_MS as _PUNCT_MAX_WAIT_MS
except Exception:  # pragma: no cover — only the import path matters
    from storage_router.sentence_buffer import (
        DEFAULT_PUNCT_MAX_WAIT_MS as _PUNCT_MAX_WAIT_MS,
    )

try:
    # Wave 8.5 — diarization gate budget. Same fallback rationale as 8.3.
    from voice_ingest.config import (
        DIARIZATION_GATE_POLL_MS as _DIARIZATION_GATE_POLL_MS,
        DIARIZATION_GATE_TIMEOUT_MS as _DIARIZATION_GATE_TIMEOUT_MS,
    )
except Exception:  # pragma: no cover
    _DIARIZATION_GATE_TIMEOUT_MS = 10_000
    _DIARIZATION_GATE_POLL_MS = 500

from storage_router.diarization_gate import gate_assign

logger = logging.getLogger(__name__)

# Each WebM chunk from the browser is exactly this long. The browser sets
# `MediaRecorder.start(timeslice=5000)` and the backend only knows the
# offset by counting chunks, not by inspecting WebM duration headers (those
# are unreliable mid-stream). If the browser-side timeslice changes, update
# this constant in lockstep.
CHUNK_DURATION_MS = 10000

router = APIRouter()

CHUNK_ROOT = Path(os.environ.get("LIVE_CHUNK_DIR", "/tmp/live-meeting-chunks"))


def _chunk_dir(meeting_id: str) -> Path:
    p = CHUNK_ROOT / meeting_id
    p.mkdir(parents=True, exist_ok=True)
    return p


def _next_chunk_seq(meeting_id: str) -> int:
    """Return the next sequence number based on existing files on disk.

    Files are named ``<seq>.webm``. Concurrent uploads from the same browser
    are unlikely (MediaRecorder dispatches sequentially), so a directory
    scan is sufficient for the stub.
    """
    d = _chunk_dir(meeting_id)
    existing = [int(p.stem) for p in d.glob("*.webm") if p.stem.isdigit()]
    return (max(existing) + 1) if existing else 0


@router.post("/api/live-meetings", status_code=201)
async def create_live_meeting(
    request: Request,
    workspace_id: str = Form(...),
    title: str = Form("Live meeting"),
    session: Session = Depends(get_session),
):
    """Create an artifact + meeting in ``status='live'``.

    Wave 8.6: also spawns the per-meeting `live-topic-tracker` tick
    loop on `app.state.live_tasks[meeting_id]["topic"]`. The task is
    cancelled by `end_live_meeting`. Spawn is best-effort: if the
    asyncio scheduler is unavailable (synchronous test client without
    a running loop) we swallow and log rather than fail the route.
    """
    artifact = storage.create_artifact(
        session,
        workspace_id=workspace_id,
        source_type="live_voice",
        capture_mode="live",
        title=title,
        created_by="u_dev",
    )
    meeting = storage.create_meeting(
        session, artifact_id=artifact.id, title=title, status="live"
    )
    session.add(
        MeetingSourceRow(
            id=new_id("ms"),
            meeting_id=meeting.id,
            source_kind="mic",
        )
    )
    session.commit()
    try:
        from storage_router.live_topic_tracker import start_topic_loop

        start_topic_loop(request.app, meeting.id)
    except RuntimeError as exc:  # no running event loop (sync test client)
        logger.info(
            "live-topic-tracker not started for %s (no event loop): %s",
            meeting.id,
            exc,
        )
    # Wave 6.3: spin up the periodic agent loop that refreshes the
    # rolling summary every ~120s. ``start_for`` is a no-op if there is
    # no running event loop (e.g., a sync test client) so we don't have
    # to special-case test wiring here.
    live_extraction.start_for(meeting.id)
    # Wave 6.4: same cadence, separate tick — drives the
    # ``live-meeting-extraction`` skill over the SINCE-marked window
    # and creates draft cards.
    live_extraction.start_extraction_for(meeting.id)
    return {
        "artifact_id": artifact.id,
        "meeting_id": meeting.id,
        "status": "live",
    }


def _get_buffer(request: Request, meeting_id: str) -> SentenceBuffer:
    """Return (or lazily create) the per-meeting sentence buffer.

    Created on first chunk; popped on `end_live_meeting`. Storage is on
    `app.state.sentence_buffers`, initialised by the app factory.
    """
    buffers: dict[str, SentenceBuffer] = request.app.state.sentence_buffers
    buf = buffers.get(meeting_id)
    if buf is None:
        buf = SentenceBuffer(punct_max_wait_ms=_PUNCT_MAX_WAIT_MS)
        buffers[meeting_id] = buf
    return buf


def _persist_sentence(
    session: Session,
    meeting_id: str,
    sentence: CompleteSentence,
    *,
    speaker_id: str = "speaker_1",
) -> SpeakerSegmentRow:
    """Insert one sentence as a `speaker_segments` row.

    Wave 8.5: `speaker_id` is supplied by the diarization gate; defaults
    to `speaker_1` only when the gate is bypassed (the `end_live_meeting`
    flush path, where pyannote has nothing more to say). The row is
    `is_final=True` because, by definition, a sentence is a final unit
    (terminal punctuation seen or force-flushed).
    """
    row = SpeakerSegmentRow(
        id=new_id("seg"),
        meeting_id=meeting_id,
        speaker_id=speaker_id,
        speaker_name=None,
        start_ms=sentence.start_ms,
        end_ms=sentence.end_ms,
        text=sentence.text,
        confidence=None,
        source_type="live_voice",
        is_final=True,
    )
    session.add(row)
    return row


def _get_diarizer(request: Request, meeting_id: str):
    """Return (or lazily create) the per-meeting `LiveDiarizer`.

    Lazy import to avoid pulling `numpy` into the import graph for
    storage-router-only test runs that never touch the live path.
    """
    diarizers: dict = request.app.state.live_diarizers
    diar = diarizers.get(meeting_id)
    if diar is None:
        from voice_ingest.live_diarize import LiveDiarizer  # lazy

        diar = LiveDiarizer(meeting_id=meeting_id)
        diarizers[meeting_id] = diar
    return diar


@router.post("/api/live-meetings/{meeting_id}/audio-chunk", status_code=202)
async def receive_chunk(
    meeting_id: str,
    request: Request,
    audio: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Persist a chunk, transcribe it via voice-ingest, and append segments.

    Returns ``{seq, segments_added, bytes}`` so the client can correlate.

    Wave 8.3: raw Whisper segments are no longer persisted directly. They
    feed a per-meeting `SentenceBuffer`; only complete sentences become
    rows in `speaker_segments`. A chunk that contains zero sentence
    terminators yields `segments_added=0` (the fragment is held until the
    next chunk completes the sentence).
    """
    meeting = session.get(MeetingRow, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    if meeting.status != "live":
        raise HTTPException(
            status_code=409,
            detail={
                "error": {"code": "not_live", "current_status": meeting.status}
            },
        )

    seq = _next_chunk_seq(meeting_id)
    blob = await audio.read()
    target = _chunk_dir(meeting_id) / f"{seq}.webm"
    target.write_bytes(blob)

    # Offset = number of completed chunks before this one. Browser-side
    # MediaRecorder uses a fixed 5s timeslice (CHUNK_DURATION_MS); voice-
    # ingest segment timestamps are 0-based for the chunk it sees, so we
    # shift them onto the meeting's running timeline.
    offset_ms = seq * CHUNK_DURATION_MS

    inserted: list[SpeakerSegmentRow] = []
    try:
        transcript = await ingest_adapter_http.transcribe_voice_file_async(target)
    except Exception as exc:  # noqa: BLE001 — any transport / 5xx error
        logger.warning(
            "voice-ingest failed for meeting=%s seq=%s: %s", meeting_id, seq, exc
        )
        # Fallback so the UI still progresses; downstream finalize can ignore
        # rows with confidence=0.0 + the placeholder text.
        fallback = SpeakerSegmentRow(
            id=new_id("seg"),
            meeting_id=meeting_id,
            speaker_id=None,
            speaker_name=None,
            start_ms=offset_ms,
            end_ms=offset_ms + CHUNK_DURATION_MS,
            text=f"[live chunk {seq} received — transcription pending]",
            confidence=0.0,
            source_type="live_voice",
            is_final=False,
        )
        session.add(fallback)
        session.commit()
        return {
            "seq": seq,
            "segments_added": 1,
            "bytes": len(blob),
            "transcribed": False,
        }

    # Wave 8.3 — convert voice-ingest segments to the buffer's input shape,
    # offset-shifted onto the meeting's running timeline, then feed the
    # per-meeting `SentenceBuffer`. Only complete sentences leave the
    # buffer and become rows.
    buffer = _get_buffer(request, meeting_id)
    feed_segments: list[WhisperSeg] = []
    for seg in transcript.segments:
        if not seg.text or not seg.text.strip():
            continue
        feed_segments.append(
            WhisperSeg(
                text=seg.text,
                start_ms=(seg.start_ms or 0) + offset_ms,
                end_ms=(seg.end_ms or 0) + offset_ms if seg.end_ms is not None else offset_ms,
            )
        )
    sentences = buffer.feed(feed_segments)
    # Wave 8.5 — gate persistence on diarization. We poll the diarizer
    # for each completed sentence (up to DIARIZATION_GATE_TIMEOUT_MS)
    # and only then insert the row. The gate falls back to
    # `speaker_id="unknown"` on timeout so the UI does not stall.
    diarizer = _get_diarizer(request, meeting_id)
    for sentence in sentences:
        gate = await gate_assign(
            diarizer,
            sentence.start_ms,
            sentence.end_ms,
            timeout_ms=_DIARIZATION_GATE_TIMEOUT_MS,
            poll_ms=_DIARIZATION_GATE_POLL_MS,
        )
        if gate.gated_unknown:
            logger.info(
                "live_route gated_unknown=true meeting=%s seq=%s text=%r wait_ms=%s",
                meeting_id,
                seq,
                sentence.text,
                gate.waited_ms,
            )
        inserted.append(
            _persist_sentence(
                session, meeting_id, sentence, speaker_id=gate.speaker_id
            )
        )
    session.commit()

    return {
        "seq": seq,
        "segments_added": len(inserted),
        "bytes": len(blob),
        "transcribed": True,
    }


@router.post("/api/live-meetings/{meeting_id}/end")
async def end_live_meeting(
    meeting_id: str,
    request: Request,
    session: Session = Depends(get_session),
):
    """Flip the meeting from ``live`` -> ``ready``.

    The downstream finalize/extract pipeline runs on its own cadence; this
    endpoint only signals that no further chunks will arrive.

    Wave 8.3: also pops the per-meeting sentence buffer and persists any
    trailing fragment as a final sentence so the last partial utterance is
    not lost.
    """
    meeting = session.get(MeetingRow, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    if meeting.status not in ("live", "ready"):
        raise HTTPException(
            status_code=409,
            detail={
                "error": {"code": "not_live", "current_status": meeting.status}
            },
        )
    # Flush + drop the buffer regardless of starting status, so a re-`/end`
    # call on a meeting that is already `ready` is still idempotent.
    buffers: dict[str, SentenceBuffer] = request.app.state.sentence_buffers
    buf = buffers.pop(meeting_id, None)
    if buf is not None:
        for sentence in buf.flush():
            # Trailing fragment on /end: skip the gate (the recording is
            # over, no further audio will arrive). Persist with the
            # current default speaker_id; a subsequent rename via
            # PATCH /api/meetings/{id}/speakers can still relabel it.
            _persist_sentence(session, meeting_id, sentence)
    # Drop the per-meeting diarizer so its rolling buffer is freed.
    request.app.state.live_diarizers.pop(meeting_id, None)
    # Wave 8.6: cancel the per-meeting topic-tracker tick loop.
    try:
        from storage_router.live_topic_tracker import cancel_topic_loop

        cancel_topic_loop(request.app, meeting_id)
    except Exception as exc:  # noqa: BLE001 — cleanup should never raise
        logger.warning("cancel_topic_loop failed for %s: %s", meeting_id, exc)
    if meeting.status == "live":
        meeting.status = "ready"
    session.commit()
    # Wave 6.3 + 6.4: tear down both agent loops. Safe to call even if
    # no task was ever started (idle no-op). The standard finalize
    # chain at /end runs the consolidation pass which dedupes any
    # cards that the live-extraction overlap window emitted twice.
    live_extraction.stop_for(meeting_id)
    live_extraction.stop_extraction_for(meeting_id)
    return {"meeting_id": meeting_id, "status": meeting.status}


@router.get("/api/live-meetings/{meeting_id}/segments")
def list_segments(
    meeting_id: str,
    since_id: str | None = None,
    session: Session = Depends(get_session),
):
    """Return the live transcript so far.

    Frontend polls this every ~2s. ``since_id`` lets callers skip rows they
    already have; absent that, callers receive the full segment list.
    Ordering is stable on the autoincrement-like primary key (``id`` is a
    monotonically-fresh ULID-ish string from ``new_id``); we order by
    ``(start_ms, id)`` so chunks land in arrival order.
    """
    meeting = session.get(MeetingRow, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    q = (
        select(SpeakerSegmentRow)
        .where(SpeakerSegmentRow.meeting_id == meeting_id)
        .order_by(SpeakerSegmentRow.start_ms.nulls_last(), SpeakerSegmentRow.id)
    )
    rows = list(session.execute(q).scalars().all())
    if since_id is not None:
        # Drop everything up to and including the caller's last-seen id.
        try:
            cut = next(i for i, r in enumerate(rows) if r.id == since_id)
            rows = rows[cut + 1 :]
        except StopIteration:
            pass

    # Wave 8.4: apply per-meeting speaker_label_map at read time so a
    # live rename never rewrites historical rows. The map's value wins
    # over a per-row `speaker_name` if both are present (the rename is
    # the user's explicit choice).
    label_map: dict[str, str] = dict(meeting.speaker_label_map or {})
    return {
        "meeting_id": meeting_id,
        "status": meeting.status,
        # Wave 6.3: bundle the rolling summary into the segments response
        # so the frontend can pick it up on the same 2s poll without a
        # second round-trip. NULL until the first agent tick succeeds.
        "live_summary": meeting.live_summary,
        "segments": [
            {
                "segment_id": r.id,
                "speaker_id": r.speaker_id,
                "speaker_name": (
                    label_map.get(r.speaker_id) if r.speaker_id else None
                ) or r.speaker_name,
                "start_ms": r.start_ms,
                "end_ms": r.end_ms,
                "text": r.text,
                "confidence": r.confidence,
                "source_type": r.source_type,
                "is_final": r.is_final,
            }
            for r in rows
        ],
    }


@router.get("/api/live-meetings/{meeting_id}/draft-cards")
def list_live_draft_cards(
    meeting_id: str,
    since_iso: str | None = None,
    session: Session = Depends(get_session),
):
    """Wave 6.4: poll for cards created by the live extraction tick.

    Returns visible (non-hidden) memory cards for the meeting in
    creation order. The ``since_iso`` query param (UTC ISO 8601) lets
    a polling caller skip cards it already has — server-side filter is
    on ``created_at > since``.

    The response shape mirrors the existing
    ``/api/meetings/{id}/memory-cards`` list endpoint so the frontend
    can reuse the same MemoryCard rendering.
    """
    from datetime import datetime

    from storage_router.models.db import MemoryCardRow
    from storage_router.api.memory_cards_route import _row_to_card

    meeting = session.get(MeetingRow, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")

    q = (
        select(MemoryCardRow)
        .where(MemoryCardRow.meeting_id == meeting_id)
        .where(MemoryCardRow.hidden_at.is_(None))
        .order_by(MemoryCardRow.created_at, MemoryCardRow.id)
    )
    if since_iso is not None:
        try:
            since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": {
                        "code": "bad_since",
                        "message": (
                            "since_iso must be ISO 8601 (e.g., "
                            "2026-05-11T12:34:56Z)"
                        ),
                    }
                },
            ) from None
        q = q.where(MemoryCardRow.created_at > since_dt)
    rows = list(session.execute(q).scalars().all())
    return {
        "meeting_id": meeting_id,
        "status": meeting.status,
        "items": [_row_to_card(r).model_dump(mode="json") for r in rows],
    }


@router.get("/api/live-meetings/{meeting_id}/summary")
def get_live_summary(meeting_id: str, session: Session = Depends(get_session)):
    """Return the most recent rolling summary for a live meeting.

    Wave 6.3: a thin read endpoint that returns whatever the periodic
    agent loop last wrote to ``meetings.live_summary``. The frontend
    can either poll this on its own cadence or read the summary that
    is now bundled into ``GET /segments`` — both surface the same value.
    """
    meeting = session.get(MeetingRow, meeting_id)
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    return {
        "meeting_id": meeting_id,
        "status": meeting.status,
        "summary": meeting.live_summary,
    }
