"""Memory-card CRUD + state transitions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.models.contracts import MemoryCard, MemoryCardState, MemoryCardType
from storage_router.models.memory_cards import (
    MemoryCardCreate,
    MemoryCardListResponse,
    MemoryCardPatch,
)

router = APIRouter()


def _row_to_card(row) -> MemoryCard:
    return MemoryCard(
        memory_card_id=row.id,
        meeting_id=row.meeting_id,
        state=MemoryCardState(row.state),
        type=MemoryCardType(row.type),
        title=row.title,
        content=row.content,
        source_chunk_ids=list(row.source_chunk_ids),
        source_start_ms=row.source_start_ms,
        source_end_ms=row.source_end_ms,
        speakers_json=list(row.speakers_json) if row.speakers_json is not None else None,
        confidence=row.confidence,
        needs_review=row.needs_review,
        created_by_agent=row.created_by_agent,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _illegal_transition(from_: str, to: str) -> JSONResponse:
    return JSONResponse(
        status_code=409,
        content={"error": {"code": "illegal_transition", "from": from_, "to": to}},
    )


@router.post("/api/memory-cards", status_code=201)
def create_card(body: MemoryCardCreate, session: Session = Depends(get_session)):
    try:
        row = storage.create_memory_card(
            session,
            meeting_id=body.meeting_id,
            type=body.type.value,
            title=body.title,
            content=body.content,
            source_chunk_ids=body.source_chunk_ids,
            confidence=body.confidence,
            source_start_ms=body.source_start_ms,
            source_end_ms=body.source_end_ms,
            speakers_json=body.speakers_json,
            needs_review=body.needs_review,
            created_by_agent=body.created_by_agent,
        )
        session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    session.refresh(row)
    return _row_to_card(row).model_dump(mode="json")


@router.get("/api/meetings/{meeting_id}/memory-cards")
def list_cards(
    meeting_id: str,
    type: MemoryCardType | None = Query(None),
    state: MemoryCardState | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    try:
        rows, total = storage.list_meeting_cards(
            session,
            meeting_id=meeting_id,
            type=type.value if type is not None else None,
            state=state.value if state is not None else None,
            limit=limit,
            offset=offset,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return MemoryCardListResponse(
        items=[_row_to_card(r) for r in rows], total=total
    ).model_dump(mode="json")


@router.patch("/api/memory-cards/{card_id}")
def patch_card(
    card_id: str,
    body: MemoryCardPatch,
    session: Session = Depends(get_session),
):
    patch = body.model_dump(exclude_unset=True)
    # Convert enum field to its string value before persisting.
    if "type" in patch and patch["type"] is not None:
        patch["type"] = (
            patch["type"].value if hasattr(patch["type"], "value") else patch["type"]
        )
    try:
        row = storage.patch_memory_card(session, card_id, patch)
        session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        if e.args and e.args[0] == "illegal_transition":
            return _illegal_transition(e.args[1], e.args[2])
        raise
    session.refresh(row)
    return _row_to_card(row).model_dump(mode="json")


def _transition(card_id: str, target: str, session: Session):
    try:
        row = storage.transition_card_state(session, card_id, target=target)
        session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        if e.args and e.args[0] == "illegal_transition":
            return _illegal_transition(e.args[1], e.args[2])
        raise
    session.refresh(row)
    return _row_to_card(row).model_dump(mode="json")


@router.post("/api/memory-cards/{card_id}/commit")
def commit_card(card_id: str, session: Session = Depends(get_session)):
    return _transition(card_id, "committed", session)


@router.post("/api/memory-cards/{card_id}/reject")
def reject_card(card_id: str, session: Session = Depends(get_session)):
    return _transition(card_id, "rejected", session)
