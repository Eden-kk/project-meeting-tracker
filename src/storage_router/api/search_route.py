"""Cross-meeting search routes (Wave 4) — Postgres FTS over speaker_segments
and memory_cards. Pure read-only, workspace-scoped, paginated.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.models.contracts import MemoryCardType
from storage_router.models.search import (
    CardSearchHit,
    CardSearchResponse,
    TranscriptSearchHit,
    TranscriptSearchResponse,
)

router = APIRouter()


@router.get("/api/search/transcripts")
def search_transcripts(
    workspace_id: str = Query(..., min_length=1),
    q: str | None = Query(None, max_length=500),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    rows, total = storage.search_segments_fts(
        session,
        workspace_id=workspace_id,
        query=q,
        limit=limit,
        offset=offset,
    )
    items = [
        TranscriptSearchHit(
            segment_id=r["segment_id"],
            meeting_id=r["meeting_id"],
            meeting_title=r.get("meeting_title") or "",
            speaker=r.get("speaker_name") or r.get("speaker_id") or "Unknown",
            start_ms=int(r.get("start_ms") or 0),
            end_ms=int(r.get("end_ms") or 0),
            text=r.get("text") or "",
            snippet=r.get("snippet") or "",
            rank=float(r.get("rank") or 0.0),
        )
        for r in rows
    ]
    return TranscriptSearchResponse(items=items, total=total).model_dump(mode="json")


@router.get("/api/search/cards")
def search_cards(
    workspace_id: str = Query(..., min_length=1),
    q: str | None = Query(None, max_length=500),
    type: MemoryCardType | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    rows, total = storage.search_cards_fts(
        session,
        workspace_id=workspace_id,
        query=q,
        type=type.value if type is not None else None,
        limit=limit,
        offset=offset,
    )
    items = [
        CardSearchHit(
            memory_card_id=r["memory_card_id"],
            meeting_id=r["meeting_id"],
            meeting_title=r.get("meeting_title") or "",
            type=MemoryCardType(r["type"]),
            title=r.get("title") or "",
            content=r.get("content") or "",
            confidence=float(r.get("confidence") or 0.0),
            source_start_ms=r.get("source_start_ms"),
            source_end_ms=r.get("source_end_ms"),
            snippet=r.get("snippet") or "",
            rank=float(r.get("rank") or 0.0),
        )
        for r in rows
    ]
    return CardSearchResponse(items=items, total=total).model_dump(mode="json")


__all__ = ["router"]
