"""Transactional repository functions over the Phase-1 ORM."""
from __future__ import annotations

from sqlalchemy import func, select

from storage_router.ids import new_id
from storage_router.models.contracts import NormalizedTranscript, SpeakerSegment, SourceType
from storage_router.models.db import (
    ConversationArtifactRow,
    MeetingRow,
    MemoryCardRow,
    SpeakerSegmentRow,
)
from storage_router.state_machine import next_status



def create_artifact(
    session,
    *,
    workspace_id: str,
    source_type: str,
    capture_mode: str,
    title: str,
    created_by: str,
    raw_file_url: str | None = None,
    raw_text: str | None = None,
    visibility: str = "private",
    labels: list[str] | None = None,
) -> ConversationArtifactRow:
    row = ConversationArtifactRow(
        id=new_id("art"),
        workspace_id=workspace_id,
        source_type=source_type,
        capture_mode=capture_mode,
        title=title,
        created_by=created_by,
        raw_file_url=raw_file_url,
        raw_text=raw_text,
        processing_status="received",
        visibility=visibility,
        labels=labels or [],
    )
    session.add(row)
    session.flush()
    return row


def create_meeting(
    session, *, artifact_id: str, title: str = "", status: str = "processing"
) -> MeetingRow:
    row = MeetingRow(id=new_id("m"), artifact_id=artifact_id, title=title, status=status)
    session.add(row)
    session.flush()
    return row


def update_processing_status(session, artifact_id: str, status: str) -> None:
    """SELECT FOR UPDATE → state-machine guard → UPDATE, all in one transaction."""
    row = session.execute(
        select(ConversationArtifactRow)
        .where(ConversationArtifactRow.id == artifact_id)
        .with_for_update()
    ).scalar_one()
    row.processing_status = next_status(row.processing_status, status)
    session.flush()


def update_meeting_status(session, meeting_id: str, status: str) -> None:
    row = session.get(MeetingRow, meeting_id)
    if row is None:
        raise LookupError(f"meeting {meeting_id} not found")
    row.status = status
    session.flush()


def persist_transcript_segments(
    session, meeting_id: str, transcript: NormalizedTranscript
) -> None:
    """Bulk insert segments. Contract segment_id is discarded; PKs are fresh."""
    rows = [
        SpeakerSegmentRow(
            id=new_id("seg"),
            meeting_id=meeting_id,
            speaker_id=seg.speaker_id,
            speaker_name=seg.speaker_name,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            text=seg.text,
            confidence=seg.confidence,
            source_type=seg.source_type.value,
            is_final=seg.is_final,
        )
        for seg in transcript.segments
    ]
    session.add_all(rows)
    session.flush()


def get_meeting(session, meeting_id: str) -> MeetingRow | None:
    return session.get(MeetingRow, meeting_id)


def list_meetings(
    session, *, workspace_id: str, limit: int = 50, offset: int = 0
) -> tuple[list[MeetingRow], int]:
    """Return (rows, total) for a workspace, newest artifact first."""
    base = (
        select(MeetingRow)
        .join(ConversationArtifactRow, MeetingRow.artifact_id == ConversationArtifactRow.id)
        .where(ConversationArtifactRow.workspace_id == workspace_id)
    )
    total = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = (
        session.execute(
            base.order_by(ConversationArtifactRow.created_at.desc(), MeetingRow.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_transcript(session, meeting_id: str) -> NormalizedTranscript:
    rows = (
        session.execute(
            select(SpeakerSegmentRow)
            .where(SpeakerSegmentRow.meeting_id == meeting_id)
            .order_by(SpeakerSegmentRow.start_ms.nulls_last(), SpeakerSegmentRow.id)
        )
        .scalars()
        .all()
    )
    segments = [
        SpeakerSegment(
            segment_id=r.id,
            speaker_id=r.speaker_id,
            speaker_name=r.speaker_name,
            start_ms=r.start_ms,
            end_ms=r.end_ms,
            text=r.text,
            confidence=r.confidence,
            source_type=SourceType(r.source_type),
            is_final=r.is_final,
        )
        for r in rows
    ]
    return NormalizedTranscript(meeting_id=meeting_id, segments=segments)


# --- memory cards ----------------------------------------------------------

def create_memory_card(
    session,
    *,
    meeting_id: str,
    type: str,
    title: str,
    content: str,
    source_chunk_ids: list[str],
    confidence: float,
    source_start_ms: int | None = None,
    source_end_ms: int | None = None,
    speakers_json: list[str] | None = None,
    created_by_agent: str | None = None,
) -> MemoryCardRow:
    """Insert a new MemoryCard. Phase-3 redesign: cards are live on insert;
    there is no `state` column, no `draft → committed` transition. The
    audit + consolidation passes flag bad cards via `hidden_at`.

    Raises LookupError if the meeting does not exist (route maps to 404).
    """
    if session.get(MeetingRow, meeting_id) is None:
        raise LookupError(f"meeting {meeting_id} not found")
    row = MemoryCardRow(
        id=new_id("mem"),
        meeting_id=meeting_id,
        type=type,
        title=title,
        content=content,
        source_chunk_ids=source_chunk_ids,
        source_start_ms=source_start_ms,
        source_end_ms=source_end_ms,
        speakers_json=speakers_json,
        confidence=confidence,
        created_by_agent=created_by_agent,
    )
    session.add(row)
    session.flush()
    return row


def list_meeting_cards(
    session,
    *,
    meeting_id: str,
    type: str | None = None,
    include_hidden: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[MemoryCardRow], int]:
    """Return (rows, total) for a meeting's cards, newest first.

    By default filters out agent-hidden rows (`hidden_at IS NULL`). Set
    `include_hidden=True` for admin / audit views.

    Raises LookupError if the meeting does not exist.
    """
    if session.get(MeetingRow, meeting_id) is None:
        raise LookupError(f"meeting {meeting_id} not found")
    base = select(MemoryCardRow).where(MemoryCardRow.meeting_id == meeting_id)
    if type is not None:
        base = base.where(MemoryCardRow.type == type)
    if not include_hidden:
        base = base.where(MemoryCardRow.hidden_at.is_(None))
    total = session.execute(
        select(func.count()).select_from(base.subquery())
    ).scalar_one()
    rows = (
        session.execute(
            base.order_by(MemoryCardRow.created_at.desc(), MemoryCardRow.id)
            .limit(limit)
            .offset(offset)
        )
        .scalars()
        .all()
    )
    return list(rows), int(total)


def get_memory_card(session, card_id: str) -> MemoryCardRow | None:
    return session.get(MemoryCardRow, card_id)
