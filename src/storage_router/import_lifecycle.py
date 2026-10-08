"""Serialized import controls; cancellation revokes local writes, not remote compute."""
from sqlalchemy import select

from storage_router.models.db import ConversationArtifactRow, MeetingRow

ACTIVE = {"received", "parsing", "transcribing", "normalizing"}
SUPPORTED = {"voice_file", "transcript_file", "pasted_transcript"}


def locked_import(session, meeting_id):
    # Use the same meeting-first order as deletion and dispatcher completion.
    meeting = session.scalar(select(MeetingRow).where(MeetingRow.id == meeting_id)
                             .with_for_update().execution_options(populate_existing=True))
    if meeting is None or meeting.deleted_at is not None:
        return None
    artifact = session.scalar(select(ConversationArtifactRow)
                              .where(ConversationArtifactRow.id == meeting.artifact_id)
                              .with_for_update().execution_options(populate_existing=True))
    if (artifact is None or artifact.capture_mode != "imported"
            or artifact.source_type not in SUPPORTED):
        return None
    return meeting, artifact


def job_state(artifact):
    return {"status": artifact.processing_status, "attempts": artifact.processing_attempts,
            "error": artifact.processing_error}


def change_job(session, meeting_id, action, remote_stopped=False):
    rows = locked_import(session, meeting_id)
    if rows is None:
        raise LookupError("import not found")
    meeting, artifact = rows
    if action == "cancel":
        if artifact.processing_status == "cancelled":
            return job_state(artifact)
        if artifact.processing_status not in ACTIVE:
            raise ValueError("Only pending or processing imports can be cancelled.")
        artifact.processing_status = meeting.status = "cancelled"
        artifact.processing_attempt = None
        artifact.processing_error = "Cancelled locally; remote computation may still be running."
    else:
        if artifact.processing_status not in {"failed", "cancelled"}:
            raise ValueError("Only failed or cancelled imports can be retried.")
        if artifact.processing_attempts and not remote_stopped:
            raise ValueError("Confirm the previous remote job has stopped before retrying.")
        artifact.processing_status = "received"
        artifact.processing_attempt = None
        artifact.processing_error = None
        meeting.status = "processing"
    session.flush()
    return job_state(artifact)
