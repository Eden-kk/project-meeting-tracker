"""Background-task dispatcher: drives an artifact through to ready/failed."""
from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path

from sqlalchemy import select

from storage_router import storage
from storage_router.db import SessionLocal
from storage_router.ingest_adapter import parse_transcript, transcribe_voice_file
from storage_router.models.contracts import NormalizedTranscript, SpeakerSegment
from storage_router.models.db import ConversationArtifactRow, MeetingRow
from storage_router.sentence_buffer import SentenceBuffer, WhisperSeg

log = logging.getLogger(__name__)

try:
    # Match the live path: use voice_ingest's tuned force-flush window when
    # available, otherwise fall through to the buffer's module default.
    from voice_ingest.config import PUNCT_MAX_WAIT_MS as _PUNCT_MAX_WAIT_MS
except Exception:  # pragma: no cover — only the import path matters
    from storage_router.sentence_buffer import (
        DEFAULT_PUNCT_MAX_WAIT_MS as _PUNCT_MAX_WAIT_MS,
    )


def _split_transcript_per_sentence(
    transcript: NormalizedTranscript,
) -> NormalizedTranscript:
    """Re-shape a freshly-ingested transcript so each segment is one sentence.

    Mirrors the live-path wiring (``api/live_route.receive_chunk``): raw
    whisper-style segments (often 5-30 s, multiple sentences each) are fed
    through a `SentenceBuffer` so only complete sentences leave the layer.

    Speaker preservation: consecutive segments sharing a `speaker_id` are
    fed through the same buffer pass; when the speaker_id changes (or the
    input ends) the buffer is flushed so an in-flight fragment is never
    stitched across a speaker turn. Each emitted sentence inherits the
    speaker_id/speaker_name/source_type/confidence/is_final of the group
    it came from.
    """
    if not transcript.segments:
        return transcript

    new_segments: list[SpeakerSegment] = []
    # Group consecutive segments by (speaker_id, speaker_name) so a turn
    # change forces a buffer flush instead of stitching across speakers.
    group: list[SpeakerSegment] = []

    def _drain(group_segs: list[SpeakerSegment]) -> None:
        if not group_segs:
            return
        # All segments in the group share these labels (by construction).
        template = group_segs[0]
        buf = SentenceBuffer(punct_max_wait_ms=_PUNCT_MAX_WAIT_MS)
        feed: list[WhisperSeg] = []
        for seg in group_segs:
            if not seg.text or not seg.text.strip():
                continue
            feed.append(
                WhisperSeg(
                    text=seg.text,
                    start_ms=int(seg.start_ms or 0),
                    end_ms=int(
                        seg.end_ms
                        if seg.end_ms is not None
                        else (seg.start_ms or 0)
                    ),
                )
            )
        emitted = list(buf.feed(feed))
        emitted.extend(buf.flush())
        for idx, sentence in enumerate(emitted):
            new_segments.append(
                SpeakerSegment(
                    segment_id=f"{template.segment_id}-s{idx}",
                    speaker_id=template.speaker_id,
                    speaker_name=template.speaker_name,
                    start_ms=sentence.start_ms,
                    end_ms=sentence.end_ms,
                    text=sentence.text,
                    confidence=template.confidence,
                    source_type=template.source_type,
                    is_final=template.is_final,
                )
            )

    for seg in transcript.segments:
        key = (seg.speaker_id, seg.speaker_name)
        if group and (group[0].speaker_id, group[0].speaker_name) != key:
            _drain(group)
            group = []
        group.append(seg)
    _drain(group)

    return transcript.model_copy(update={"segments": new_segments})


def _path_from_file_url(url: str) -> Path:
    return Path(urllib.parse.urlparse(url).path)  # TODO(s3): download to tmp file.


def _detect_format(text: str) -> str:
    lines = [ln for ln in text.splitlines() if ln.strip()]
    if not lines:
        return "txt"
    if lines[0].strip().upper().startswith("WEBVTT"):
        return "vtt"
    # SRT: first non-empty line is a numeric counter, second is timing.
    if lines[0].strip().isdigit() and len(lines) > 1 and "-->" in lines[1]:
        return "srt"
    return "txt"


def process_artifact(
    artifact_id: str,
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> None:
    """Drive the artifact through the state machine. Background-task entry.

    Speaker hints (forwarded to pyannote when the source_type is voice_file)
    let the caller override pyannote's auto-cluster when the expected count
    is known — pyannote under-counts on short or code-switched recordings.
    """
    with SessionLocal() as session:
        artifact = session.get(ConversationArtifactRow, artifact_id)
        if artifact is None:
            log.warning("dispatcher: artifact %s missing", artifact_id)
            return
        meeting = session.execute(
            select(MeetingRow).where(MeetingRow.artifact_id == artifact_id)
        ).scalar_one_or_none()
        if meeting is None:
            log.warning("dispatcher: no meeting for artifact %s", artifact_id)
            return
        meeting_id = meeting.id

        try:
            if artifact.source_type == "voice_file":
                storage.update_processing_status(session, artifact_id, "transcribing")
                session.commit()
                transcript = transcribe_voice_file(
                    _path_from_file_url(artifact.raw_file_url),
                    num_speakers=num_speakers,
                    min_speakers=min_speakers,
                    max_speakers=max_speakers,
                )
                # Parity with the live path: per-sentence rows, not raw
                # multi-sentence whisper chunks. See `api/live_route.receive_chunk`.
                transcript = _split_transcript_per_sentence(transcript)
            elif artifact.source_type == "transcript_file":
                storage.update_processing_status(session, artifact_id, "parsing")
                session.commit()
                transcript = parse_transcript(
                    artifact.raw_text,
                    format=_detect_format(artifact.raw_text or ""),
                    source_type="transcript_file",
                )
            elif artifact.source_type == "pasted_transcript":
                storage.update_processing_status(session, artifact_id, "parsing")
                session.commit()
                transcript = parse_transcript(
                    artifact.raw_text,
                    format=_detect_format(artifact.raw_text or ""),
                    source_type="pasted_transcript",
                )
            else:
                raise ValueError(f"unsupported source_type {artifact.source_type}")

            transcript = transcript.model_copy(update={"meeting_id": meeting_id})
            storage.update_processing_status(session, artifact_id, "normalizing")
            session.commit()
            storage.persist_transcript_segments(session, meeting_id, transcript)
            storage.update_processing_status(session, artifact_id, "ready")
            storage.update_meeting_status(session, meeting_id, "ready")
            session.commit()
        except Exception:
            log.exception("dispatcher: failed for artifact %s", artifact_id)
            session.rollback()
            try:
                artifact = session.get(ConversationArtifactRow, artifact_id)
                if artifact is not None:
                    artifact.processing_status = "failed"
                m = session.execute(
                    select(MeetingRow).where(MeetingRow.artifact_id == artifact_id)
                ).scalar_one_or_none()
                if m is not None:
                    m.status = "failed"
                session.commit()
            except Exception:
                log.exception("dispatcher: also failed to mark failed for %s", artifact_id)
                session.rollback()
            return

    # Phase-3 auto-finalize: outside the parsing transaction, fire
    # Hermes finalize. The runtime opens its own session and walks
    # status through `finalizing → finalized`, or reverts to `ready`
    # with last_finalize_error set on failure. Inline-import the runtime
    # so test monkeypatches against
    # `storage_router.hermes_runtime.auto_finalize_meeting` take effect.
    from storage_router import hermes_runtime

    try:
        hermes_runtime.auto_finalize_meeting(meeting_id)
    except Exception:  # noqa: BLE001 — must not crash the dispatcher.
        log.exception(
            "dispatcher: auto-finalize raised for meeting %s", meeting_id
        )
