"""FastAPI surface for transcript-ingest.

POST /transcript/parse — multipart upload OR pasted text → NormalizedTranscript.
GET  /healthz         — liveness probe.

Error contract:
  - 400: neither file nor text provided
  - 422: parser rejected the input (caller-fixable)
  - 500: orchestrator output failed schema validation (internal bug — do not retry)
"""
from __future__ import annotations

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from jsonschema import ValidationError

from .orchestrator import parse_transcript

app = FastAPI(title="transcript-ingest", version="0.1.0")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.post("/transcript/parse")
async def transcript_parse(
    file: UploadFile | None = File(default=None),
    text: str | None = Form(default=None),
    meeting_id: str | None = Form(default=None),
    format_hint: str | None = Form(default=None),
) -> dict:
    if file is None and not text:
        raise HTTPException(status_code=400, detail="either 'file' or 'text' is required")

    if file is not None:
        payload: str | bytes = await file.read()
        filename_hint = file.filename
    else:
        payload = text or ""
        filename_hint = None

    try:
        return parse_transcript(
            payload,
            format_hint=format_hint,
            meeting_id=meeting_id,
            filename_hint=filename_hint,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except ValidationError as e:
        raise HTTPException(status_code=500, detail=f"normalized output failed schema: {e.message}")
