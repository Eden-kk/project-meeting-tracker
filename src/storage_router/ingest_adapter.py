"""Switch between stub and real ingest packages by INGEST_BACKEND."""
from __future__ import annotations

from storage_router.config import settings

if settings.ingest_backend == "real":
    from voice_ingest import transcribe_voice_file  # type: ignore[import-not-found]
    from transcript_ingest import parse_transcript  # type: ignore[import-not-found]
else:
    from storage_router.ingest_stubs.voice_ingest import transcribe_voice_file
    from storage_router.ingest_stubs.transcript_ingest import parse_transcript

__all__ = ["transcribe_voice_file", "parse_transcript"]
