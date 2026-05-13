"""Pydantic v2 models for hermes-plugin tool inputs/outputs.

Mirrors `schemas/memory_card.schema.json`, `schemas/normalized_transcript.schema.json`,
and `schemas/speaker_segment.schema.json`. The module-level
``TOOL_JSON_SCHEMAS`` dict is what the Anthropic SDK consumes as each
tool's ``input_schema``.
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field

CardType = Literal[
    "decision",
    "action_item",
    "pain_point",
    "quote",
    "requirement",
    "risk",
    "open_question",
    "technical_detail",
]

SourceType = Literal[
    "live_voice",
    "zoom_rtms",
    "voice_file",
    "transcript_file",
    "pasted_transcript",
]


class SpeakerSegment(BaseModel):
    """One speaker turn within a normalized transcript."""

    model_config = ConfigDict(extra="forbid")

    segment_id: str = Field(min_length=1)
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    start_ms: Optional[int] = Field(default=None, ge=0)
    end_ms: Optional[int] = Field(default=None, ge=0)
    text: str
    confidence: Optional[float] = Field(default=None, ge=0, le=1)
    source_type: SourceType
    is_final: bool


class NormalizedTranscript(BaseModel):
    """Unified transcript shape returned by GET /api/meetings/{id}/transcript."""

    model_config = ConfigDict(extra="forbid")

    meeting_id: str = Field(min_length=1)
    segments: list[SpeakerSegment]


class MemoryCard(BaseModel):
    """Evidence-backed memory item; mirrors memory_card.schema.json.

    Phase-3 redesign: dropped `state` enum and `needs_review`. Quality is
    owned by the agent passes via `confidence`, `hidden_at`, and
    `superseded_by_id`.
    """

    model_config = ConfigDict(extra="forbid")

    memory_card_id: str = Field(min_length=1)
    meeting_id: str = Field(min_length=1)
    type: CardType
    title: str = Field(min_length=1, max_length=500)
    content: str
    source_chunk_ids: list[str] = Field(min_length=1)
    source_start_ms: Optional[int] = Field(default=None, ge=0)
    source_end_ms: Optional[int] = Field(default=None, ge=0)
    speakers_json: Optional[list[str]] = None
    confidence: float = Field(ge=0, le=1)
    hidden_at: Optional[str] = None
    superseded_by_id: Optional[str] = None
    audit_reason: Optional[str] = None
    created_by_agent: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


# ---- Tool input/output models ----


class GetMeetingTranscriptInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(min_length=1)


GetMeetingTranscriptOutput = NormalizedTranscript


class SearchMemoryCardsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(min_length=1)
    type: Optional[CardType] = None
    include_hidden: Optional[bool] = False


class SearchMemoryCardsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cards: list[MemoryCard]


class CreateDraftMemoryCardInput(BaseModel):
    """Input for create_draft_memory_card.

    Field names mirror memory_card.schema.json exactly (notably
    ``speakers_json``, not ``speakers``) because the wire payload
    rejects unknown keys.
    """

    model_config = ConfigDict(extra="forbid")

    meeting_id: str = Field(min_length=1)
    type: CardType
    title: str = Field(min_length=1, max_length=500)
    content: str
    source_chunk_ids: list[str] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    source_start_ms: Optional[int] = Field(default=None, ge=0)
    source_end_ms: Optional[int] = Field(default=None, ge=0)
    speakers_json: Optional[list[str]] = None


CreateDraftMemoryCardOutput = MemoryCard


class FinalizeMeetingMemoryInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(min_length=1)


class UpdateCardConfidenceInput(BaseModel):
    """Wave 2.1 audit-pass tool: downgrade a card's confidence in place."""

    model_config = ConfigDict(extra="forbid")
    card_id: str = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)
    reason: str = Field(min_length=1, max_length=2000)


UpdateCardConfidenceOutput = MemoryCard


class HideCardInput(BaseModel):
    """Wave 2.1 audit-pass tool: soft-delete a card unsupported by evidence."""

    model_config = ConfigDict(extra="forbid")
    card_id: str = Field(min_length=1)
    reason: str = Field(min_length=1, max_length=2000)


HideCardOutput = MemoryCard


class SupersedeCardInput(BaseModel):
    """Wave 2.2 consolidation-pass tool: merge `loser` into `winner`."""

    model_config = ConfigDict(extra="forbid")
    loser_id: str = Field(min_length=1)
    winner_id: str = Field(min_length=1)


class SupersedeCardOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loser_id: str
    winner_id: str
    winner_source_chunk_ids: list[str]


class FinalizeMeetingMemoryOutput(BaseModel):
    """Cross-worktree contract with worktree G (memory-cards-backend).

    If G ships POST /api/meetings/{id}/finalize with a different shape,
    this model and the corresponding mock-transport assertions update
    in lockstep.
    """

    model_config = ConfigDict(extra="forbid")

    meeting_id: str = Field(min_length=1)
    finalized_at: str
    committed_card_ids: list[str]


# Wave 4.3 — cross-meeting search tools for the `workspace-qa` skill.


class SearchWorkspaceTranscriptsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1)
    q: Optional[str] = Field(default=None, max_length=500)
    limit: Optional[int] = Field(default=10, ge=1, le=50)


class SearchWorkspaceTranscriptsHit(BaseModel):
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


class SearchWorkspaceTranscriptsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[SearchWorkspaceTranscriptsHit]
    total: int = 0


class SearchWorkspaceCardsInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    workspace_id: str = Field(min_length=1)
    q: Optional[str] = Field(default=None, max_length=500)
    type: Optional[CardType] = None
    limit: Optional[int] = Field(default=10, ge=1, le=50)


class SearchWorkspaceCardsHit(BaseModel):
    model_config = ConfigDict(extra="forbid")
    memory_card_id: str
    meeting_id: str
    meeting_title: str = ""
    type: CardType
    title: str
    content: str
    confidence: float = 0.0
    source_start_ms: Optional[int] = None
    source_end_ms: Optional[int] = None
    snippet: str = ""
    rank: float = 0.0


class SearchWorkspaceCardsOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    items: list[SearchWorkspaceCardsHit]
    total: int = 0


TOOL_JSON_SCHEMAS: dict[str, dict] = {
    "get_meeting_transcript": GetMeetingTranscriptInput.model_json_schema(),
    "search_memory_cards": SearchMemoryCardsInput.model_json_schema(),
    "create_draft_memory_card": CreateDraftMemoryCardInput.model_json_schema(),
    "finalize_meeting_memory": FinalizeMeetingMemoryInput.model_json_schema(),
    "update_card_confidence": UpdateCardConfidenceInput.model_json_schema(),
    "hide_card": HideCardInput.model_json_schema(),
    "supersede_card": SupersedeCardInput.model_json_schema(),
    "search_workspace_transcripts": SearchWorkspaceTranscriptsInput.model_json_schema(),
    "search_workspace_cards": SearchWorkspaceCardsInput.model_json_schema(),
}


__all__ = [
    "CardType",
    "SourceType",
    "SpeakerSegment",
    "NormalizedTranscript",
    "MemoryCard",
    "GetMeetingTranscriptInput",
    "GetMeetingTranscriptOutput",
    "SearchMemoryCardsInput",
    "SearchMemoryCardsOutput",
    "CreateDraftMemoryCardInput",
    "CreateDraftMemoryCardOutput",
    "FinalizeMeetingMemoryInput",
    "FinalizeMeetingMemoryOutput",
    "UpdateCardConfidenceInput",
    "UpdateCardConfidenceOutput",
    "HideCardInput",
    "HideCardOutput",
    "SupersedeCardInput",
    "SupersedeCardOutput",
    "SearchWorkspaceTranscriptsInput",
    "SearchWorkspaceTranscriptsOutput",
    "SearchWorkspaceCardsInput",
    "SearchWorkspaceCardsOutput",
    "TOOL_JSON_SCHEMAS",
]
