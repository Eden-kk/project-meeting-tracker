"""Local-development import status, cancellation and explicit retry controls."""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel, ConfigDict, StrictBool
from sqlalchemy import select

from storage_router.db import SessionLocal
from storage_router.import_lifecycle import SUPPORTED, change_job, job_state
from storage_router.models.db import ConversationArtifactRow, MeetingRow

router = APIRouter(prefix="/api/meetings/{meeting_id}/import-job")


class RetryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    remote_stopped: StrictBool = False


@router.get("")
def get_job(meeting_id: str):
    with SessionLocal() as session:
        artifact = session.scalar(select(ConversationArtifactRow).join(MeetingRow)
            .where(MeetingRow.id == meeting_id, MeetingRow.deleted_at.is_(None),
                   ConversationArtifactRow.capture_mode == "imported",
                   ConversationArtifactRow.source_type.in_(SUPPORTED)))
        if artifact is None:
            raise HTTPException(404, "import not found")
        return job_state(artifact)


def _change(meeting_id, action, remote_stopped=False):
    with SessionLocal.begin() as session:
        try:
            return change_job(session, meeting_id, action, remote_stopped)
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc


@router.post("/cancel")
def cancel_job(meeting_id: str):
    return _change(meeting_id, "cancel")


@router.post("/retry", status_code=202)
def retry_job(meeting_id: str, body: RetryBody, background_tasks: BackgroundTasks):
    result = _change(meeting_id, "retry", body.remote_stopped)
    # The durable received state also survives a lost background callback.
    with SessionLocal() as session:
        artifact_id = session.scalar(select(MeetingRow.artifact_id).where(MeetingRow.id == meeting_id))
    from storage_router.dispatcher import process_artifact
    background_tasks.add_task(process_artifact, artifact_id)
    return result
