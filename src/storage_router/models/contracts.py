# Generated from schemas/*.schema.json via scripts/codegen_models.sh, then
# manually consolidated to a single module: cross-file $refs in jsonschema
# produce a multi-file output that we collapse here so importers see one
# canonical SourceType / SpeakerSegment definition.
#
# Re-running codegen produces the per-file output; copy each class into this
# file (in the order below) and dedupe enums.

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import AnyUrl, BaseModel, ConfigDict, Field


class SourceType(Enum):
    live_voice = "live_voice"
    zoom_rtms = "zoom_rtms"
    voice_file = "voice_file"
    transcript_file = "transcript_file"
    pasted_transcript = "pasted_transcript"


class CaptureMode(Enum):
    live = "live"
    imported = "imported"


class Visibility(Enum):
    private = "private"
    workspace = "workspace"
    shared = "shared"


class ProcessingStatus(Enum):
    received = "received"
    transcribing = "transcribing"
    diarizing = "diarizing"
    parsing = "parsing"
    normalizing = "normalizing"
    extracting = "extracting"
    ready = "ready"
    failed = "failed"


class MeetingStatus(Enum):
    live = "live"
    processing = "processing"
    ready = "ready"
    finalizing = "finalizing"
    finalized = "finalized"
    failed = "failed"


class EvidenceQuality(Enum):
    """Per design-doc §9 evidence-quality table."""

    unknown = "unknown"
    high = "high"
    medium = "medium"
    low = "low"
    lowest = "lowest"


class MemoryCardType(Enum):
    decision = "decision"
    action_item = "action_item"
    pain_point = "pain_point"
    quote = "quote"
    requirement = "requirement"
    risk = "risk"
    open_question = "open_question"
    technical_detail = "technical_detail"


class SpeakerSegment(BaseModel):
    """One speaker turn within a normalized transcript. Source of truth: design-doc §9."""

    model_config = ConfigDict(extra="forbid")
    segment_id: str = Field(..., min_length=1)
    speaker_id: str | None = Field(
        None,
        description=(
            "Diarization-assigned id (e.g. speaker_1) or 'unknown' for "
            "transcript-only inputs without speaker info."
        ),
    )
    speaker_name: str | None = None
    start_ms: int | None = Field(
        None,
        description="Null when source has no timestamps (e.g. pasted_transcript without timing).",
        ge=0,
    )
    end_ms: int | None = Field(None, ge=0)
    text: str
    confidence: float | None = Field(None, ge=0.0, le=1.0)
    source_type: SourceType
    is_final: bool = Field(
        ...,
        description="False for interim live STT output; true for finalized turns and any imported segment.",
    )


class NormalizedTranscript(BaseModel):
    """Unified transcript object every input path must produce. Source of truth: design-doc §9."""

    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(..., min_length=1)
    segments: list[SpeakerSegment]


class MeetingPattern(BaseModel):
    """Hermes-inferred description of a meeting's character; design-doc §12.1."""

    model_config = ConfigDict(extra="forbid")
    primary_pattern: str = Field(
        ...,
        description="Open-ended label, e.g. customer_discovery_call, group_sync, technical_review.",
    )
    secondary_patterns: list[str] | None = Field([], description="Phase 4+. Empty in Phase 2.")
    interaction_style: str | None = Field(None, description="Phase 4+. Null in Phase 2.")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reason: str | None = Field(None, description="Phase 4+. Null in Phase 2.")


class Meeting(BaseModel):
    """Processing/finalization record built on a ConversationArtifact. Source of truth: design-doc §8.

    Phase-3 auto-finalize adds the `finalizing` status (between `ready`
    and `finalized`) and the `last_finalize_error` field — populated when
    the background finalize task fails so the status reverts to `ready`
    and the cause is visible without log-diving.
    """

    model_config = ConfigDict(extra="forbid")
    meeting_id: str = Field(..., min_length=1)
    artifact_id: str = Field(..., min_length=1)
    title: str = ""
    status: MeetingStatus
    started_at: datetime | None = None
    ended_at: datetime | None = None
    finalized_at: datetime | None = None
    detected_pattern: MeetingPattern | None = None
    current_schema: dict[str, Any] | None = Field(
        None,
        description="The selected_blocks object Hermes is currently using for this meeting; see design-doc §12.",
    )
    evidence_quality: EvidenceQuality = Field(
        ..., description="Per design-doc §9 evidence-quality table."
    )
    last_finalize_error: str | None = Field(
        None,
        description=(
            "Set by the auto-finalize background task when finalize fails; "
            "status reverts to `ready` so the user can re-trigger."
        ),
    )
    speaker_label_map: dict[str, str] | None = Field(
        None,
        description=(
            "Wave 8.4: per-meeting friendly speaker names "
            "({'speaker_2': 'Alice', ...}). Applied at read time on "
            "/api/live-meetings/{id}/segments so renaming does not rewrite "
            "historical rows."
        ),
    )


class ConversationArtifact(BaseModel):
    """Top-level record for any input the system has accepted. Source of truth: design-doc §8."""

    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(..., min_length=1)
    workspace_id: str = Field(..., min_length=1)
    source_type: SourceType
    capture_mode: CaptureMode
    title: str = Field(..., max_length=500, min_length=1)
    created_by: str = Field(..., min_length=1)
    created_at: datetime
    visibility: Visibility
    labels: list[str] | None = []
    raw_file_url: AnyUrl | None = Field(
        None,
        description="Set for voice_file and zoom_rtms recordings; null for transcript-only inputs.",
    )
    raw_text: str | None = Field(
        None,
        description="Set for transcript_file and pasted_transcript inputs; null otherwise.",
    )
    processing_status: ProcessingStatus


class MemoryCard(BaseModel):
    """Evidence-backed memory item Hermes extracts from a meeting. Source of truth: design-doc §13.

    Phase-3 redesign: dropped `state` enum and `needs_review`; added
    `hidden_at` (agent soft-delete) and `superseded_by_id` (agent dedupe
    pointer at the canonical winner card).
    """

    model_config = ConfigDict(extra="forbid")
    memory_card_id: str = Field(..., min_length=1)
    meeting_id: str = Field(..., min_length=1)
    type: MemoryCardType
    title: str = Field(..., max_length=500, min_length=1)
    content: str
    source_chunk_ids: list[str] = Field(..., min_length=1)
    source_start_ms: int | None = Field(None, ge=0)
    source_end_ms: int | None = Field(None, ge=0)
    speakers_json: list[str] | None = Field(
        None,
        description="List of speaker names/ids implicated by this card; mirrors speaker_segments rows.",
    )
    confidence: float = Field(..., ge=0.0, le=1.0)
    hidden_at: datetime | None = Field(
        None,
        description=(
            "Agent-driven soft delete; list endpoints filter `hidden_at IS NULL` by default."
        ),
    )
    superseded_by_id: str | None = Field(
        None,
        description=(
            "If set, points at the canonical winner card from the agent consolidation pass."
        ),
    )
    audit_reason: str | None = Field(
        None,
        description=(
            "Free-text rationale recorded by the agent audit pass when it "
            "downgrades confidence or hides a card. Surfaced for debugging."
        ),
    )
    created_by_agent: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "CaptureMode",
    "ConversationArtifact",
    "EvidenceQuality",
    "Meeting",
    "MeetingPattern",
    "MeetingStatus",
    "MemoryCard",
    "MemoryCardType",
    "NormalizedTranscript",
    "ProcessingStatus",
    "SourceType",
    "SpeakerSegment",
    "Visibility",
]
