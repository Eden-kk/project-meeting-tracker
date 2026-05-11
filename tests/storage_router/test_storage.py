"""Round-trip tests for storage.py against the live Postgres."""
from __future__ import annotations

import pytest

from storage_router.models.contracts import (
    NormalizedTranscript,
    SourceType,
    SpeakerSegment,
)
from storage_router.storage import (
    create_artifact,
    create_meeting,
    get_meeting,
    get_transcript,
    persist_transcript_segments,
    update_meeting_status,
    update_processing_status,
)


def _make_segment(idx: int) -> SpeakerSegment:
    return SpeakerSegment(
        segment_id=f"seg_input_{idx}",
        speaker_id=f"speaker_{idx}",
        speaker_name=f"S{idx}",
        start_ms=idx * 1000,
        end_ms=idx * 1000 + 500,
        text=f"hello {idx}",
        confidence=None,
        source_type=SourceType.transcript_file,
        is_final=True,
    )


def test_create_artifact_and_meeting(db_session) -> None:
    art = create_artifact(
        db_session,
        workspace_id="ws_dev",
        source_type="pasted_transcript",
        capture_mode="imported",
        title="t1",
        created_by="u_dev",
        raw_text="hi",
    )
    db_session.commit()
    assert art.id.startswith("art_")
    assert art.processing_status == "received"
    assert art.visibility == "private"
    assert art.labels == []

    m = create_meeting(db_session, artifact_id=art.id)
    db_session.commit()
    assert m.id.startswith("m_")
    assert m.status == "processing"
    assert m.evidence_quality == "unknown"


def test_state_machine_guards_processing_status(db_session) -> None:
    art = create_artifact(
        db_session,
        workspace_id="ws_dev",
        source_type="pasted_transcript",
        capture_mode="imported",
        title="t",
        created_by="u_dev",
        raw_text="x",
    )
    db_session.commit()
    update_processing_status(db_session, art.id, "parsing")
    db_session.commit()
    with pytest.raises(ValueError, match="illegal transition"):
        update_processing_status(db_session, art.id, "ready")


def test_persist_and_get_transcript_round_trip(db_session) -> None:
    art = create_artifact(
        db_session,
        workspace_id="ws_dev",
        source_type="transcript_file",
        capture_mode="imported",
        title="t",
        created_by="u_dev",
        raw_text="hi",
    )
    m = create_meeting(db_session, artifact_id=art.id)
    db_session.commit()

    segments = [_make_segment(i) for i in (1, 2, 3)]
    transcript = NormalizedTranscript(meeting_id=m.id, segments=segments)
    persist_transcript_segments(db_session, m.id, transcript)
    db_session.commit()

    out = get_transcript(db_session, m.id)
    assert out.meeting_id == m.id
    assert len(out.segments) == 3
    # PKs are regenerated; original segment_id is discarded by design.
    for original, returned in zip(segments, out.segments, strict=True):
        assert returned.segment_id != original.segment_id
        assert returned.segment_id.startswith("seg_")
        assert returned.text == original.text
        assert returned.start_ms == original.start_ms
        assert returned.source_type == original.source_type
        assert returned.is_final is True


def test_get_meeting_returns_none_for_missing(db_session) -> None:
    assert get_meeting(db_session, "m_does_not_exist") is None


def test_update_meeting_status(db_session) -> None:
    art = create_artifact(
        db_session,
        workspace_id="ws_dev",
        source_type="pasted_transcript",
        capture_mode="imported",
        title="t",
        created_by="u_dev",
        raw_text="x",
    )
    m = create_meeting(db_session, artifact_id=art.id)
    db_session.commit()
    update_meeting_status(db_session, m.id, "ready")
    db_session.commit()
    assert get_meeting(db_session, m.id).status == "ready"
