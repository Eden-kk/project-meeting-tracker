"""JSON parser — passthrough with default-filling.

Accepts either `{meeting_id, segments}` or a bare `list[segment]`. Returns the
segment list with required fields defaulted; the orchestrator will overwrite
`source_type` and wrap with `meeting_id`.
"""
from __future__ import annotations

import json


def parse_json(text: str) -> list[dict]:
    data = json.loads(text)
    if isinstance(data, dict) and "segments" in data:
        raw_segments = data["segments"]
    elif isinstance(data, list):
        raw_segments = data
    else:
        raise ValueError("json transcript must be an object with 'segments' or a list")

    if not isinstance(raw_segments, list):
        raise ValueError("'segments' must be a list")

    segments: list[dict] = []
    for i, seg in enumerate(raw_segments, start=1):
        if not isinstance(seg, dict):
            raise ValueError(f"segment {i} is not an object")
        out = {
            "segment_id": seg.get("segment_id") or f"seg_{i:03d}",
            "speaker_id": seg.get("speaker_id"),
            "speaker_name": seg.get("speaker_name"),
            "start_ms": seg.get("start_ms"),
            "end_ms": seg.get("end_ms"),
            "text": seg.get("text", ""),
            "confidence": seg.get("confidence"),
            "is_final": seg.get("is_final", True),
        }
        segments.append(out)
    return segments
