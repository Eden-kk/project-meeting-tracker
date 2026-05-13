"""GET /api/meetings list, GET /api/meetings/{id}, GET /api/meetings/{id}/transcript."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.models.contracts import Meeting, MeetingStatus
from storage_router.models.db import MeetingRow

router = APIRouter()


def _meeting_to_contract(row) -> Meeting:
    return Meeting(
        meeting_id=row.id,
        artifact_id=row.artifact_id,
        title=row.title,
        status=MeetingStatus(row.status),
        started_at=row.started_at,
        ended_at=row.ended_at,
        finalized_at=row.finalized_at,
        detected_pattern=None,
        current_schema=row.current_schema,
        evidence_quality=row.evidence_quality,
        last_finalize_error=row.last_finalize_error,
        speaker_label_map=row.speaker_label_map,
        current_topic=row.current_topic,
        finalized_summary=row.finalized_summary,
    )


class SpeakerRenameBody(BaseModel):
    """Wave 8.4 — body for `PATCH /api/meetings/{id}/speakers`.

    `from` is a Python reserved keyword so we expose it via an alias.
    `populate_by_name=True` lets test fixtures pass `from_=...` while
    real HTTP clients send the wire name `from`.
    """

    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    from_: str = Field(..., alias="from", min_length=1)
    to: str = Field(..., min_length=1)


@router.get("/api/meetings")
def list_meetings(
    workspace_id: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    rows, total = storage.list_meetings(
        session, workspace_id=workspace_id, limit=limit, offset=offset
    )
    return {
        "items": [_meeting_to_contract(r).model_dump(mode="json") for r in rows],
        "total": total,
    }


@router.get("/api/meetings/{meeting_id}")
def get_meeting(meeting_id: str, session: Session = Depends(get_session)):
    row = storage.get_meeting(session, meeting_id)
    if row is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    return _meeting_to_contract(row).model_dump(mode="json")


@router.get("/api/meetings/{meeting_id}/transcript")
def get_transcript(meeting_id: str, session: Session = Depends(get_session)):
    row = storage.get_meeting(session, meeting_id)
    if row is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    if row.status not in {"ready", "finalizing", "finalized", "live"}:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "not_ready", "current_status": row.status}},
        )
    transcript = storage.get_transcript(session, meeting_id)
    # Apply speaker_label_map at read time — same logic as the live /segments
    # endpoint — so renaming a speaker is reflected in the transcript tab
    # without rewriting historical speaker_segments rows.
    label_map: dict[str, str] = dict(row.speaker_label_map or {})
    if label_map:
        patched_segments = [
            seg.model_copy(
                update={
                    "speaker_name": (
                        label_map.get(seg.speaker_id) if seg.speaker_id else None
                    )
                    or seg.speaker_name
                }
            )
            for seg in transcript.segments
        ]
        transcript = transcript.model_copy(update={"segments": patched_segments})
    return transcript.model_dump(mode="json")


@router.delete("/api/meetings/{meeting_id}")
def delete_meeting(request: Request, meeting_id: str, session: Session = Depends(get_session)):
    result = storage.soft_delete_meeting(session, meeting_id)
    if result is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    meeting, raw_file_url, was_newly_deleted = result
    if not was_newly_deleted:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "already_deleted", "message": "meeting already deleted"}},
        )
    session.commit()
    blob_removed = False
    if raw_file_url:
        store = request.app.state.blob_store
        blob_removed = store.delete(raw_file_url)
    return {
        "meeting_id": meeting.id,
        "deleted_at": meeting.deleted_at.isoformat(),
        "blob_removed": blob_removed,
    }


@router.patch("/api/meetings/{meeting_id}/speakers")
def rename_speaker(
    meeting_id: str,
    body: SpeakerRenameBody,
    session: Session = Depends(get_session),
):
    """Wave 8.4 — set / update one entry of `meetings.speaker_label_map`.

    The map is applied at read time on `/segments` so this update never
    touches historical `speaker_segments` rows. Idempotent: re-renaming
    the same `from` overwrites the previous `to`.
    """
    row = session.get(MeetingRow, meeting_id)
    if row is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    current = dict(row.speaker_label_map or {})
    current[body.from_] = body.to
    row.speaker_label_map = current
    session.commit()
    return _meeting_to_contract(row).model_dump(mode="json")
