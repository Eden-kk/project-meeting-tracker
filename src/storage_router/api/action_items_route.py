"""Cross-meeting action-items + open-questions dashboards (Wave 5.1, 5.2).

These two endpoints share `storage.list_action_items`; the route layer is
the thin shape adapter. Each row carries the source meeting's title +
`finalized_at` so the frontend table can show "where this came from"
without a second round-trip.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from storage_router import storage
from storage_router.db import get_session
from storage_router.models.contracts import MemoryCardType

router = APIRouter()


class ActionItemRow(BaseModel):
    """One row in the cross-meeting dashboard. Flattens MemoryCard +
    meeting metadata into a single shape so the table component does
    not need to fetch the meeting separately."""

    model_config = ConfigDict(extra="forbid")

    memory_card_id: str
    meeting_id: str
    meeting_title: str
    meeting_finalized_at: datetime | None
    type: MemoryCardType
    title: str
    content: str
    source_chunk_ids: list[str]
    source_start_ms: int | None = None
    source_end_ms: int | None = None
    speakers_json: list[str] | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ActionItemListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[ActionItemRow]
    total: int = Field(..., ge=0)


def _list(
    *,
    type: str,
    workspace_id: str,
    speaker: str | None,
    meeting_id: str | None,
    since: datetime | None,
    until: datetime | None,
    limit: int,
    offset: int,
    session: Session,
) -> dict:
    items, total = storage.list_action_items(
        session,
        workspace_id=workspace_id,
        type=type,
        speaker=speaker,
        meeting_id=meeting_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
    )
    return ActionItemListResponse(
        items=[ActionItemRow(**row) for row in items], total=total
    ).model_dump(mode="json")


@router.get("/api/action-items")
def list_action_items(
    workspace_id: str = Query(..., min_length=1),
    speaker: str | None = Query(None),
    meeting_id: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    return _list(
        type="action_item",
        workspace_id=workspace_id,
        speaker=speaker,
        meeting_id=meeting_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        session=session,
    )


@router.get("/api/open-questions")
def list_open_questions(
    workspace_id: str = Query(..., min_length=1),
    speaker: str | None = Query(None),
    meeting_id: str | None = Query(None),
    since: datetime | None = Query(None),
    until: datetime | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_session),
):
    """Mirrors `/api/action-items` but filtered to `type=open_question`.

    Same shape, same filters — the frontend reuses the dashboard table
    component and only swaps the route + page title (Wave 5.2).
    """
    return _list(
        type="open_question",
        workspace_id=workspace_id,
        speaker=speaker,
        meeting_id=meeting_id,
        since=since,
        until=until,
        limit=limit,
        offset=offset,
        session=session,
    )
