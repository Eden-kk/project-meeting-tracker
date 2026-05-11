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
    returns from `meeting_finalization`. Server assigns id/state/timestamps."""

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
    needs_review: bool = True
    created_by_agent: str | None = None


class MemoryCardPatch(BaseModel):
    """Partial update for a draft MemoryCard. State transitions go through
    commit/reject — `state` is intentionally not in the whitelist."""

    model_config = ConfigDict(extra="forbid")

    type: MemoryCardType | None = None
    title: str | None = Field(None, min_length=1, max_length=500)
    content: str | None = None
    source_chunk_ids: list[str] | None = Field(None, min_length=1)
    source_start_ms: int | None = Field(None, ge=0)
    source_end_ms: int | None = Field(None, ge=0)
    speakers_json: list[str] | None = None
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    needs_review: bool | None = None


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
    # Number of transcript chunks the chunked extractor processed.
    # Defaults to 1 so the legacy single-pass path still validates.
    chunks_processed: int = Field(1, ge=0)


class QARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=4000)


class QAEvidenceItem(BaseModel):
    """Frontend's EvidenceCitation shape (see src/api/memory_cards.types.ts)."""
    model_config = ConfigDict(extra="forbid")
    segment_id: str = Field(..., min_length=1)
    speaker: str
    start_ms: int = Field(0, ge=0)
    end_ms: int = Field(0, ge=0)
    text: str


class QAResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    confidence: float = Field(0.85, ge=0.0, le=1.0)
    citations: list[QAEvidenceItem] = Field(default_factory=list)
    weak_evidence: bool = False


__all__ = [
    "FinalizeResponse",
    "MemoryCardCreate",
    "MemoryCardListResponse",
    "MemoryCardOut",
    "MemoryCardPatch",
    "QAEvidenceItem",
    "QARequest",
    "QAResponse",
]
