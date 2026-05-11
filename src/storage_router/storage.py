"""Transactional repository functions over the Phase-1 ORM."""
from __future__ import annotations

from sqlalchemy import select

from storage_router.ids import new_id
from storage_router.models.contracts import NormalizedTranscript, SpeakerSegment, SourceType
from storage_router.models.db import (
    ConversationArtifactRow,
    MeetingRow,
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
