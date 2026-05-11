"""SQLAlchemy ORM mirror of migrations/*.sql (Phase-1 subset)."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ConversationArtifactRow(Base):
    __tablename__ = "conversation_artifacts"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        Text, ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    capture_mode: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    raw_file_url: Mapped[str | None] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(Text)
    processing_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="received"
    )
    visibility: Mapped[str] = mapped_column(Text, nullable=False, server_default="private")
    labels: Mapped[list] = mapped_column(JSONB, nullable=False, server_default="[]")


class MeetingRow(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    artifact_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("conversation_artifacts.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False, server_default="")
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detected_pattern: Mapped[dict | None] = mapped_column(JSONB)
    # `current_schema` is quoted in the SQL; SQLAlchemy quotes per-dialect already.
    current_schema: Mapped[dict | None] = mapped_column("current_schema", JSONB)
    evidence_quality: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="unknown"
    )
    finalized_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class MeetingSourceRow(Base):
    __tablename__ = "meeting_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        Text, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    source_kind: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ParticipantRow(Base):
    __tablename__ = "participants"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        Text, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[str | None] = mapped_column(Text, ForeignKey("users.id"))
    display_name: Mapped[str | None] = mapped_column(Text)
    speaker_label: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SpeakerSegmentRow(Base):
    __tablename__ = "speaker_segments"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        Text, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    speaker_id: Mapped[str | None] = mapped_column(Text)
    speaker_name: Mapped[str | None] = mapped_column(Text)
    start_ms: Mapped[int | None] = mapped_column(BigInteger)
    end_ms: Mapped[int | None] = mapped_column(BigInteger)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float | None] = mapped_column(Double)
    source_type: Mapped[str] = mapped_column(Text, nullable=False)
    is_final: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class MemoryCardRow(Base):
    """Mirror of migrations/0004_memory.sql + 0010_collapse_card_state.sql.

    Phase-3 redesign collapsed the user-curation state machine: there is no
    `state` enum and no `needs_review` flag. Quality is owned by the agent
    audit + consolidation passes which write `confidence`, `hidden_at`,
    and `superseded_by_id`.
    """

    __tablename__ = "memory_cards"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    meeting_id: Mapped[str] = mapped_column(
        Text, ForeignKey("meetings.id", ondelete="CASCADE"), nullable=False
    )
    type: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    source_chunk_ids: Mapped[list] = mapped_column(JSONB, nullable=False)
    source_start_ms: Mapped[int | None] = mapped_column(BigInteger)
    source_end_ms: Mapped[int | None] = mapped_column(BigInteger)
    speakers_json: Mapped[list | None] = mapped_column(JSONB)
    confidence: Mapped[float] = mapped_column(Double, nullable=False)
    hidden_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    superseded_by_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("memory_cards.id", ondelete="SET NULL")
    )
    created_by_agent: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
