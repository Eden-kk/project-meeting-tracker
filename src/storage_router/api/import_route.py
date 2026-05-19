"""POST /api/conversations/import — multipart artifact router."""
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, File, Form, Request, UploadFile

from storage_router import storage
from storage_router.api.errors import bad_request
from storage_router.db import SessionLocal

router = APIRouter()


def _upload_present(upload: UploadFile | None) -> bool:
    """An UploadFile is 'present' iff filename is non-empty AND stream has bytes."""
    if upload is None or not upload.filename:
        return False
    pos = upload.file.tell()
    upload.file.seek(0, 2)  # to end
    size = upload.file.tell()
    upload.file.seek(pos)
    return size > 0


def _paste_present(text: str | None) -> bool:
    return bool(text and text.strip())


@router.post("/api/conversations/import", status_code=202)
async def import_conversation(
    request: Request,
    background_tasks: BackgroundTasks,
    workspace_id: str = Form(...),
    title: str = Form(...),
    visibility: str = Form("private"),
    labels: list[str] = Form(default_factory=list),
    voice_file: UploadFile | None = File(None),
    transcript_file: UploadFile | None = File(None),
    pasted_transcript: str | None = Form(None),
    num_speakers: int | None = Form(None),
    min_speakers: int | None = Form(None),
    max_speakers: int | None = Form(None),
):
    voice_p = _upload_present(voice_file)
    txt_p = _upload_present(transcript_file)
    paste_p = _paste_present(pasted_transcript)
    n = sum([voice_p, txt_p, paste_p])
    if n == 0:
        return bad_request(
            "no_input", "exactly one of voice_file, transcript_file, pasted_transcript required"
        )
    if n > 1:
        return bad_request(
            "multiple_inputs",
            "only one of voice_file, transcript_file, pasted_transcript may be provided",
        )

    blob_store = request.app.state.blob_store
    raw_file_url: str | None = None
    raw_text: str | None = None
    if voice_p:
        raw_file_url = blob_store.put(
            voice_file.file,
            key_hint=voice_file.filename or "voice",
            content_type=voice_file.content_type,
        )
        source_type = "voice_file"
        source_kind = "file_upload"
    elif txt_p:
        raw_bytes = transcript_file.file.read()
        try:
            raw_text = raw_bytes.decode("utf-8")
        except UnicodeDecodeError:
            return bad_request("invalid_format", "transcript_file must be UTF-8")
        source_type = "transcript_file"
        source_kind = "file_upload"
    else:
        raw_text = pasted_transcript
        source_type = "pasted_transcript"
        source_kind = "paste"

    # TODO(auth): Phase-1 hardcoded user.
    with SessionLocal() as session:
        artifact = storage.create_artifact(
            session,
            workspace_id=workspace_id,
            source_type=source_type,
            capture_mode="imported",
            title=title,
            created_by="u_dev",
            raw_file_url=raw_file_url,
            raw_text=raw_text,
            visibility=visibility,
            labels=labels,
        )
        meeting = storage.create_meeting(session, artifact_id=artifact.id, title=title)
        from storage_router.ids import new_id
        from storage_router.models.db import MeetingSourceRow

        session.add(
            MeetingSourceRow(
                id=new_id("ms"),
                meeting_id=meeting.id,
                source_kind=source_kind,
            )
        )
        session.commit()
        artifact_id, meeting_id = artifact.id, meeting.id

    # Commit before scheduling the background task: the dispatcher opens its
    # own session and must observe the rows.
    from storage_router.dispatcher import process_artifact

    background_tasks.add_task(
        process_artifact,
        artifact_id,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )

    return {
        "artifact_id": artifact_id,
        "meeting_id": meeting_id,
        "processing_status": "received",
    }
