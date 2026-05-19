"""HTTP-based adapter for the voice/transcript ingest services.

Each service runs in its own venv on a fixed loopback port; storage-router
POSTs to them so a Whisper crash never takes down the API.  Loopback HTTP
is ~5 ms; insignificant against per-second STT cost.

Per-route timeouts: voice_ingest is slow (Whisper) and gets the long
ceiling; transcript_ingest is sub-second and gets a tight one.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

from storage_router.config import settings
from storage_router.models.contracts import NormalizedTranscript


def transcribe_voice_file(
    path: Path,
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> NormalizedTranscript:
    """POST the audio bytes to voice-ingest as multipart; return the parsed transcript.

    voice-ingest's API takes a single multipart field named ``audio``
    (UploadFile) plus optional ``meeting_id`` / ``num_speakers`` /
    ``min_speakers`` / ``max_speakers`` form fields. The speaker hints
    forward to pyannote — when the caller knows the expected count,
    pyannote forces exact clustering and dramatically improves accuracy
    on short or code-switched recordings where its auto-cluster
    under-counts.

    ``follow_redirects=True``: when voice-ingest is hosted on Modal and a
    request runs longer than Modal's HTTP-sync window (~150 s, common for
    mp4 + Whisper-large-v3), Modal returns a 303 See Other pointing at a
    ``?__modal_function_call_id=…`` polling URL. httpx defaults to NOT
    following redirects on POST, so the response is mistakenly treated
    as a 3xx error and the artifact ends up in `failed`.
    """
    url = settings.voice_ingest_url.rstrip("/") + "/voice/transcribe"
    data: dict[str, str] = {}
    if num_speakers is not None:
        data["num_speakers"] = str(int(num_speakers))
    if min_speakers is not None:
        data["min_speakers"] = str(int(min_speakers))
    if max_speakers is not None:
        data["max_speakers"] = str(int(max_speakers))
    with open(path, "rb") as f:
        files = {"audio": (path.name, f, "audio/webm")}
        resp = httpx.post(
            url,
            files=files,
            data=data or None,
            timeout=settings.voice_ingest_timeout_seconds,
            follow_redirects=True,
        )
    resp.raise_for_status()
    return NormalizedTranscript.model_validate(resp.json())


async def transcribe_voice_file_async(
    path: Path,
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> NormalizedTranscript:
    """Async wrapper: runs the blocking httpx.post in a thread so the event
    loop is not stalled during Whisper STT (which can take many seconds).

    Callers in async route handlers MUST use this variant so that concurrent
    requests (e.g. a second audio-chunk or /end) are not blocked.
    """
    return await asyncio.to_thread(
        transcribe_voice_file,
        path,
        num_speakers=num_speakers,
        min_speakers=min_speakers,
        max_speakers=max_speakers,
    )


def parse_transcript(
    payload: str | bytes,
    format: str,
    *,
    source_type: str = "transcript_file",
) -> NormalizedTranscript:
    """POST the raw text to transcript-ingest as multipart form; return the parsed transcript.

    transcript-ingest's API takes ``text`` (Form), ``file`` (UploadFile, optional),
    ``meeting_id`` (Form), and ``format_hint`` (Form). It does NOT accept JSON.
    The ``source_type`` arg is ignored — transcript-ingest infers it from
    content shape (txt/md → pasted_transcript; vtt/srt/json → transcript_file).
    """
    url = settings.transcript_ingest_url.rstrip("/") + "/transcript/parse"
    body = payload.decode("utf-8") if isinstance(payload, bytes) else payload
    data = {"text": body}
    if format:
        data["format_hint"] = format
    resp = httpx.post(
        url,
        data=data,
        timeout=settings.transcript_ingest_timeout_seconds,
    )
    resp.raise_for_status()
    return NormalizedTranscript.model_validate(resp.json())
