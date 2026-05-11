"""HTTP-based adapter for the voice/transcript ingest services.

Each service runs in its own venv on a fixed loopback port; storage-router
POSTs to them so a Whisper crash never takes down the API.  Loopback HTTP
is ~5 ms; insignificant against per-second STT cost.

Per-route timeouts: voice_ingest is slow (Whisper) and gets the long
ceiling; transcript_ingest is sub-second and gets a tight one.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from storage_router.config import settings
from storage_router.models.contracts import NormalizedTranscript


def transcribe_voice_file(path: Path) -> NormalizedTranscript:
    """POST the audio bytes to voice-ingest; return the parsed transcript."""
    url = settings.voice_ingest_url.rstrip("/") + "/voice/transcribe"
    with open(path, "rb") as f:
        files = {"file": (path.name, f, "application/octet-stream")}
        resp = httpx.post(url, files=files, timeout=settings.voice_ingest_timeout_seconds)
    resp.raise_for_status()
    return NormalizedTranscript.model_validate(resp.json())


def parse_transcript(
    payload: str | bytes,
    format: str,
    *,
    source_type: str = "transcript_file",
) -> NormalizedTranscript:
    """POST the raw text to transcript-ingest; return the parsed transcript."""
    url = settings.transcript_ingest_url.rstrip("/") + "/transcript/parse"
    body = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    resp = httpx.post(
        url,
        json={"text": body, "format": format, "source_type": source_type},
        timeout=settings.transcript_ingest_timeout_seconds,
    )
    resp.raise_for_status()
    return NormalizedTranscript.model_validate(resp.json())
