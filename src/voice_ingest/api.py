"""FastAPI surface for voice-file transcription."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import jsonschema
from fastapi import FastAPI, File, Form, HTTPException, UploadFile

from . import config
from .transcribe import transcribe_voice_file

app = FastAPI(title="voice-ingest", version="0.1.0")

_DECODE_HINTS = ("ffmpeg", "could not decode", "invalid data", "format")


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "model": config.WHISPER_MODEL}


@app.post("/voice/transcribe")
async def transcribe(
    audio: UploadFile = File(...),
    meeting_id: str | None = Form(None),
) -> dict:
    suffix = Path(audio.filename or "upload.wav").suffix or ".wav"
    tmp = tempfile.NamedTemporaryFile(suffix=suffix, delete=False)
    bytes_written = 0
    try:
        while chunk := await audio.read(1 << 20):
            bytes_written += len(chunk)
            if bytes_written > config.MAX_UPLOAD_BYTES:
                raise HTTPException(413, detail="upload exceeds MAX_UPLOAD_BYTES")
            tmp.write(chunk)
        tmp.close()

        try:
            return transcribe_voice_file(tmp.name, meeting_id=meeting_id)
        except jsonschema.ValidationError as exc:
            raise HTTPException(500, detail=f"schema validation failed: {exc.message}")
        except (RuntimeError, ValueError, OSError) as exc:
            msg = str(exc).lower()
            if any(h in msg for h in _DECODE_HINTS):
                raise HTTPException(415, detail=str(exc))
            raise
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


__all__ = ["app"]
