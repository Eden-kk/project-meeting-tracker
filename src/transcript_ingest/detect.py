"""Format detection for transcript payloads.

First match wins: filename hint → content sniff → text fallback.
"""
from __future__ import annotations

import json
import re
from typing import Literal

Format = Literal["vtt", "srt", "txt", "md", "json"]

_EXT_MAP: dict[str, Format] = {
    ".vtt": "vtt",
    ".srt": "srt",
    ".json": "json",
    ".md": "md",
    ".markdown": "md",
    ".txt": "txt",
}

_SRT_CUE_RE = re.compile(
    r"^\s*\d+\s*\n\d{2}:\d{2}:\d{2},\d{3}\s*-->\s*\d{2}:\d{2}:\d{2},\d{3}",
    re.MULTILINE,
)

_MD_MARKER_RE = re.compile(r"(^|\n)(#{1,6}\s|\>\s|\*\*[^*]+\*\*)")


def detect_format(payload: str | bytes, filename_hint: str | None = None) -> Format:
    text = payload.decode("utf-8", errors="replace") if isinstance(payload, bytes) else payload

    if filename_hint:
        lower = filename_hint.lower()
        for ext, fmt in _EXT_MAP.items():
            if lower.endswith(ext):
                return fmt

    stripped = text.lstrip()
    if stripped.startswith("WEBVTT"):
        return "vtt"

    if stripped[:1] in ("{", "["):
        try:
            json.loads(stripped)
            return "json"
        except ValueError:
            pass

    if _SRT_CUE_RE.search(text):
        return "srt"

    if _MD_MARKER_RE.search(text):
        return "md"

    return "txt"
