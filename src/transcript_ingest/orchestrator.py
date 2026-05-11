"""Top-level orchestrator: detect → parse → tag source_type → validate."""
from __future__ import annotations

from uuid import uuid4

from . import schema
from .detect import detect_format
from .parsers.json_parser import parse_json
from .parsers.srt import parse_srt
from .parsers.txt import parse_txt
from .parsers.vtt import parse_vtt

_FILE_TYPES = {"vtt", "srt", "json"}


def parse_transcript(
    payload: str | bytes,
    format_hint: str | None = None,
    meeting_id: str | None = None,
    filename_hint: str | None = None,
) -> dict:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload
    fmt = format_hint or detect_format(text, filename_hint)

    if fmt == "vtt":
        segments = parse_vtt(text)
    elif fmt == "srt":
        segments = parse_srt(text)
    elif fmt == "json":
        segments = parse_json(text)
    elif fmt in ("txt", "md"):
        segments = parse_txt(text)
    else:
        raise ValueError(f"unsupported format: {fmt!r}")

    source_type = "transcript_file" if fmt in _FILE_TYPES else "pasted_transcript"
    for seg in segments:
        seg["source_type"] = source_type

    result = {
        "meeting_id": meeting_id or f"m_{uuid4().hex[:12]}",
        "segments": segments,
    }
    schema.validate(result)
    return result
