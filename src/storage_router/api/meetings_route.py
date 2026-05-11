"""GET /api/meetings list, GET /api/meetings/{id}, GET /api/meetings/{id}/transcript."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.models.contracts import Meeting, MeetingStatus

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
    )


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
    if row.status not in {"ready", "finalized"}:
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "not_ready", "current_status": row.status}},
        )
    return storage.get_transcript(session, meeting_id).model_dump(mode="json")
