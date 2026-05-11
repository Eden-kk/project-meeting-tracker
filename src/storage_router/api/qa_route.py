"""Hermes-backed finalize + QA endpoints.

Both routes resolve the Hermes plugin at call-time via
`storage_router.hermes_runtime`; tests monkeypatch `run_meeting_finalization`
and `run_meeting_qa` to inject stub responses without installing a plugin.
"""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from storage_router import hermes_runtime, storage
from storage_router.api.memory_cards_route import _row_to_card
from storage_router.db import get_session
from storage_router.models.db import MeetingRow
from storage_router.models.memory_cards import (
    FinalizeResponse,
    MemoryCardCreate,
    QARequest,
    QAResponse,
)

router = APIRouter()


def _hermes_unavailable(exc: hermes_runtime.HermesUnavailable) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"error": {"code": "hermes_unavailable", "message": str(exc)}},
    )


@router.post("/api/meetings/{meeting_id}/finalize")
def finalize_meeting(meeting_id: str, session: Session = Depends(get_session)):
    meeting = session.execute(
        select(MeetingRow).where(MeetingRow.id == meeting_id).with_for_update()
    ).scalar_one_or_none()
    if meeting is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    if meeting.status == "finalized":
        return JSONResponse(
            status_code=409,
            content={"error": {"code": "already_finalized"}},
        )

    try:
        result = hermes_runtime.run_meeting_finalization(meeting_id)
    except hermes_runtime.HermesUnavailable as e:
        return _hermes_unavailable(e)

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

    finalized_at = datetime.now(UTC)
    meeting.status = "finalized"
    meeting.finalized_at = finalized_at
    session.commit()

    return FinalizeResponse(
        meeting_id=meeting_id,
        finalized_at=finalized_at,
        cards_created=len(cards_in),
        summary=result.get("summary", ""),
    ).model_dump(mode="json")


@router.post("/api/qa/meeting")
def qa_meeting(body: QARequest, session: Session = Depends(get_session)):
    if session.get(MeetingRow, body.meeting_id) is None:
        raise HTTPException(status_code=404, detail="meeting not found")
    try:
        result = hermes_runtime.run_meeting_qa(body.meeting_id, body.question)
    except hermes_runtime.HermesUnavailable as e:
        return _hermes_unavailable(e)
    return QAResponse(**result).model_dump(mode="json")


# Re-export for parity with cards_route's _row_to_card (kept reachable for tests).
__all__ = ["router", "_row_to_card"]
