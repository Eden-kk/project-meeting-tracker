"""Switch between stub and HTTP ingest backends by INGEST_BACKEND.

The "real" path used to import the ingest packages directly into this
process; that conflated venvs and let a Whisper crash kill the API.  We
now POST to the per-service HTTP surfaces over loopback.  The stub path
stays for unit tests so they don't need ingest services running.
"""
from __future__ import annotations

from storage_router.config import settings

if settings.ingest_backend == "real":
    from storage_router.ingest_adapter_http import (
        parse_transcript,
        transcribe_voice_file,
    )
else:
    from storage_router.ingest_stubs.voice_ingest import transcribe_voice_file
    from storage_router.ingest_stubs.transcript_ingest import parse_transcript

__all__ = ["transcribe_voice_file", "parse_transcript"]
