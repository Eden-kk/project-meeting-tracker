"""Pydantic in/out models for the memory-cards + QA endpoints.

The on-the-wire MemoryCard contract lives in `models.contracts.MemoryCard`
(generated from `schemas/memory_card.schema.json`); this module only defines
the request/response wrappers the routes consume.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from storage_router.models.contracts import MemoryCard, MemoryCardType

# Server-shaped output is the canonical contract.
MemoryCardOut = MemoryCard


class MemoryCardCreate(BaseModel):
    """Request body for POST /api/memory-cards. Also the per-card payload Hermes
    returns from `meeting_finalization`. Server assigns id + timestamps.

    Phase-3 redesign: no `state`, no `needs_review`. Cards are live as soon
    as they are created; the audit + consolidation passes flag bad cards
    via `hidden_at` / `superseded_by_id`.
    """

    model_config = ConfigDict(extra="forbid")

    meeting_id: str = Field(..., min_length=1)
    type: MemoryCardType
    title: str = Field(..., min_length=1, max_length=500)
    content: str
    source_chunk_ids: list[str] = Field(..., min_length=1)
    source_start_ms: int | None = Field(None, ge=0)
    source_end_ms: int | None = Field(None, ge=0)
    speakers_json: list[str] | None = None
    confidence: float = Field(..., ge=0.0, le=1.0)
    created_by_agent: str | None = None


class MemoryCardListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[MemoryCard]
    total: int = Field(..., ge=0)


class FinalizeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str
    finalized_at: datetime
    cards_created: int = Field(..., ge=0)
    summary: str


class QARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=4000)


class QAEvidenceItem(BaseModel):
    model_config = ConfigDict(extra="forbid")
    chunk_id: str = Field(..., min_length=1)
    text: str
    speaker: str | None = None
    start_ms: int | None = Field(None, ge=0)
    end_ms: int | None = Field(None, ge=0)


class QAResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    evidence: list[QAEvidenceItem]


__all__ = [
    "FinalizeResponse",
    "MemoryCardCreate",
    "MemoryCardListResponse",
    "MemoryCardOut",
    "QAEvidenceItem",
    "QARequest",
    "QAResponse",
]
