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


class MemoryCardConfidencePatch(BaseModel):
    """Body for PATCH /api/memory-cards/{id}/confidence (audit pass)."""

    model_config = ConfigDict(extra="forbid")

    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str | None = Field(None, max_length=2000)


class MemoryCardHideRequest(BaseModel):
    """Body for POST /api/memory-cards/{id}/hide (audit pass)."""

    model_config = ConfigDict(extra="forbid")

    reason: str | None = Field(None, max_length=2000)


class SupersedeResponse(BaseModel):
    """Response body for POST /api/memory-cards/{loser}/supersede-into/{winner}."""

    model_config = ConfigDict(extra="forbid")

    loser_id: str
    winner_id: str
    winner_source_chunk_ids: list[str]


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


# Wave 4.3 — workspace-wide QA shapes.


class WorkspaceQARequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(..., min_length=1)
    question: str = Field(..., min_length=1, max_length=4000)


class WorkspaceQACitation(BaseModel):
    """Cross-meeting citation. One of `memory_card_id` or `segment_id` is
    populated depending on whether the answer came from a card or a
    raw transcript segment. The frontend uses the populated id +
    `meeting_id` to build a deep link.
    """

    model_config = ConfigDict(extra="forbid")
    meeting_id: str
    meeting_title: str = ""
    memory_card_id: str | None = None
    segment_id: str | None = None
    snippet: str = ""


class WorkspaceQAResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    answer: str
    confidence: float = Field(0.6, ge=0.0, le=1.0)
    citations: list[WorkspaceQACitation] = Field(default_factory=list)
    weak_evidence: bool = False


__all__ = [
    "FinalizeResponse",
    "MemoryCardConfidencePatch",
    "MemoryCardCreate",
    "MemoryCardHideRequest",
    "MemoryCardListResponse",
    "MemoryCardOut",
    "QAEvidenceItem",
    "QARequest",
    "QAResponse",
    "SupersedeResponse",
    "WorkspaceQACitation",
    "WorkspaceQARequest",
    "WorkspaceQAResponse",
]
