"""Memory-card create + list routes.

Phase-3 redesign: no per-card state machine, no review surface. Cards are
live the moment they are created. The audit + consolidation passes (later
features) flag bad cards via `hidden_at` / `superseded_by_id`. The list
endpoint hides those rows by default.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.models.contracts import MemoryCard, MemoryCardType
from storage_router.models.memory_cards import (
    MemoryCardConfidencePatch,
    MemoryCardCreate,
    MemoryCardHideRequest,
    MemoryCardListResponse,
    SupersedeResponse,
)

router = APIRouter()


def _row_to_card(row) -> MemoryCard:
    return MemoryCard(
        memory_card_id=row.id,
        meeting_id=row.meeting_id,
        type=MemoryCardType(row.type),
        title=row.title,
        content=row.content,
        source_chunk_ids=list(row.source_chunk_ids),
        source_start_ms=row.source_start_ms,
        source_end_ms=row.source_end_ms,
        speakers_json=list(row.speakers_json) if row.speakers_json is not None else None,
        confidence=row.confidence,
        hidden_at=row.hidden_at,
        superseded_by_id=row.superseded_by_id,
        audit_reason=row.audit_reason,
        created_by_agent=row.created_by_agent,
        created_at=row.created_at,
        updated_at=row.updated_at,
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
    include_hidden: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    try:
        rows, total = storage.list_meeting_cards(
            session,
            meeting_id=meeting_id,
            type=type.value if type is not None else None,
            include_hidden=include_hidden,
            limit=limit,
            offset=offset,
        )
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    return MemoryCardListResponse(
        items=[_row_to_card(r) for r in rows], total=total
    ).model_dump(mode="json")


@router.patch("/api/memory-cards/{card_id}/confidence")
def patch_card_confidence(
    card_id: str,
    body: MemoryCardConfidencePatch,
    session: Session = Depends(get_session),
):
    """Wave 2.1: agent audit pass updates a card's confidence in-place.

    Sets `audit_reason` if supplied so the rationale is durable.
    """
    try:
        row = storage.update_card_confidence(
            session,
            card_id=card_id,
            confidence=body.confidence,
            reason=body.reason,
        )
        session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from None
    session.refresh(row)
    return _row_to_card(row).model_dump(mode="json")


@router.post("/api/memory-cards/{card_id}/hide")
def hide_card_route(
    card_id: str,
    body: MemoryCardHideRequest | None = None,
    session: Session = Depends(get_session),
):
    """Wave 2.1: agent audit pass soft-deletes a card.

    Sets `hidden_at = NOW()` and persists the rationale to `audit_reason`.
    Idempotent: calling twice does not flip the timestamp.
    """
    reason = body.reason if body is not None else None
    try:
        row = storage.hide_card(session, card_id=card_id, reason=reason)
        session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    session.refresh(row)
    return _row_to_card(row).model_dump(mode="json")


@router.post("/api/memory-cards/{loser_id}/supersede-into/{winner_id}")
def supersede_card_route(
    loser_id: str,
    winner_id: str,
    session: Session = Depends(get_session),
):
    """Wave 2.2: agent consolidation pass merges two near-duplicate cards.

    Sets `loser.superseded_by_id = winner_id`, hides the loser, and
    appends loser source_chunk_ids onto the winner (deduplicated).
    """
    try:
        loser, winner = storage.supersede_cards(
            session, loser_id=loser_id, winner_id=winner_id
        )
        session.commit()
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e)) from None
    session.refresh(winner)
    return SupersedeResponse(
        loser_id=loser.id,
        winner_id=winner.id,
        winner_source_chunk_ids=list(winner.source_chunk_ids),
    ).model_dump(mode="json")
