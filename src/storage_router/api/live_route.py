"""Live capture routes — Phase 3 Wave 6.1 stub.

Browser-side `MediaRecorder` POSTs ~5s WebM chunks to this service. For 6.1
we persist each chunk to a temp dir and emit a placeholder
``speaker_segments`` row. Wave 6.2 swaps the placeholder for a real STT call
by handing the blob to ``ingest_adapter_http.transcribe_voice_file``.

Routes:
    POST /api/live-meetings                                  -> create
    POST /api/live-meetings/{meeting_id}/audio-chunk         -> persist + stub segment
    POST /api/live-meetings/{meeting_id}/end                 -> flip status to ready
    GET  /api/live-meetings/{meeting_id}/segments[?since=]   -> poll transcript
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.ids import new_id
from storage_router.models.db import (
    MeetingRow,
    MeetingSourceRow,
    SpeakerSegmentRow,
)

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
def create_live_meeting(
    workspace_id: str = Form(...),
    title: str = Form("Live meeting"),
    session: Session = Depends(get_session),
):
    """Create an artifact + meeting in ``status='live'``."""
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
    return {
        "artifact_id": artifact.id,
        "meeting_id": meeting.id,
        "status": "live",
    }


@router.post("/api/live-meetings/{meeting_id}/audio-chunk", status_code=202)
async def receive_chunk(
    meeting_id: str,
    audio: UploadFile = File(...),
    session: Session = Depends(get_session),
):
    """Persist a single WebM chunk + emit a placeholder segment row.

    Returns ``{seq, segment_id}`` so the client can correlate uploads.
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

    seg = SpeakerSegmentRow(
        id=new_id("seg"),
        meeting_id=meeting_id,
        speaker_id=None,
        speaker_name=None,
        start_ms=seq * 5000,
        end_ms=(seq + 1) * 5000,
        text=f"[live chunk {seq} received]",
        confidence=None,
        source_type="live_voice",
        is_final=False,
    )
    session.add(seg)
    session.commit()

    return {
        "seq": seq,
        "segment_id": seg.id,
        "bytes": len(blob),
    }


@router.post("/api/live-meetings/{meeting_id}/end")
def end_live_meeting(meeting_id: str, session: Session = Depends(get_session)):
    """Flip the meeting from ``live`` -> ``ready``.

    The downstream finalize/extract pipeline runs on its own cadence; this
    endpoint only signals that no further chunks will arrive.
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
    if meeting.status == "live":
        meeting.status = "ready"
        session.commit()
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

    return {
        "meeting_id": meeting_id,
        "status": meeting.status,
        "segments": [
            {
                "segment_id": r.id,
                "speaker_id": r.speaker_id,
                "speaker_name": r.speaker_name,
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
