"""Stub for worktree B's voice_ingest.transcribe_voice_file."""
from __future__ import annotations

import json
from pathlib import Path

from storage_router.models.contracts import NormalizedTranscript, SourceType

# Fixtures live at the repo (worktree) root.
_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "expected_normalized.json"


def transcribe_voice_file(
    path: Path,
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> NormalizedTranscript:
    """Return a canned NormalizedTranscript with source_type=voice_file.

    Speaker hint kwargs are accepted for signature parity with the HTTP
    adapter; the stub ignores them since it returns a fixed fixture.
    """
    with open(_FIXTURE) as f:
        data = json.load(f)
    nt = NormalizedTranscript.model_validate(data)
    new_segments = [
        seg.model_copy(update={"source_type": SourceType.voice_file}) for seg in nt.segments
    ]
    # meeting_id placeholder; the dispatcher overwrites it.
    return nt.model_copy(update={"meeting_id": "__placeholder__", "segments": new_segments})
