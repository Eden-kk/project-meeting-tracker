"""Stub for worktree C's transcript_ingest.parse_transcript."""
from __future__ import annotations

import json
from pathlib import Path

from storage_router.models.contracts import NormalizedTranscript, SourceType

_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "expected_normalized.json"


def parse_transcript(
    payload: str | bytes, format: str, *, source_type: str = "transcript_file"
) -> NormalizedTranscript:
    """Return the canned fixture; payload + format are ignored in the stub."""
    with open(_FIXTURE) as f:
        data = json.load(f)
    nt = NormalizedTranscript.model_validate(data)
    st = SourceType(source_type)
    new_segments = [seg.model_copy(update={"source_type": st}) for seg in nt.segments]
    return nt.model_copy(update={"meeting_id": "__placeholder__", "segments": new_segments})
