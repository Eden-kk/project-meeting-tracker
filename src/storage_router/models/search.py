"""Pydantic response models for cross-meeting search endpoints (Wave 4).

These are read-only response shapes returned by
``/api/search/transcripts`` and ``/api/search/cards``.
"""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, ConfigDict

from storage_router.models.contracts import MemoryCardType


class TranscriptSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segment_id: str
    meeting_id: str
    meeting_title: str = ""
    speaker: str = ""
    start_ms: int = 0
    end_ms: int = 0
    text: str
    snippet: str = ""
    rank: float = 0.0


class TranscriptSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[TranscriptSearchHit]
    total: int = 0


class CardSearchHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    memory_card_id: str
    meeting_id: str
    meeting_title: str = ""
    type: MemoryCardType
    title: str
    content: str
    confidence: float = 0.0
    source_start_ms: Optional[int] = None
    source_end_ms: Optional[int] = None
    snippet: str = ""
    rank: float = 0.0


class CardSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[CardSearchHit]
    total: int = 0


__all__ = [
    "TranscriptSearchHit",
    "TranscriptSearchResponse",
    "CardSearchHit",
    "CardSearchResponse",
]
