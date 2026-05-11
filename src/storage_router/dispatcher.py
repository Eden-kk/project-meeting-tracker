"""Background-task dispatcher: drives an artifact through to ready/failed."""
from __future__ import annotations

import logging
import urllib.parse
from pathlib import Path

from sqlalchemy import select

from storage_router import storage
from storage_router.db import SessionLocal
from storage_router.ingest_adapter import parse_transcript, transcribe_voice_file
from storage_router.models.db import ConversationArtifactRow, MeetingRow

log = logging.getLogger(__name__)


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


def process_artifact(artifact_id: str) -> None:
    """Drive the artifact through the state machine. Background-task entry."""
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
                transcript = transcribe_voice_file(_path_from_file_url(artifact.raw_file_url))
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
