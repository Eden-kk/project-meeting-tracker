"""Plain-text / markdown parser — line-by-line `Name: text`, no timestamps.

Markdown markers (`#`, `>`, `**bold**`) are stripped before line splitting so a
markdown-flavored paste still produces speaker-prefixed lines.
"""
from __future__ import annotations

import re

from ._speakers import make_speaker_registry

_SPEAKER_RE = re.compile(r"^([A-Z][a-zA-Z0-9 _.'-]{0,40}):\s*(.+)$")
_MD_HEAD_RE = re.compile(r"^\s{0,3}(#{1,6}\s+|>\s+)")
_MD_BOLD_RE = re.compile(r"\*\*([^*]+)\*\*")


def _strip_md(line: str) -> str:
    line = _MD_HEAD_RE.sub("", line)
    line = _MD_BOLD_RE.sub(r"\1", line)
    return line


def parse_txt(text: str) -> list[dict]:
    assign = make_speaker_registry()
    segments: list[dict] = []
    i = 0
    for raw_line in text.splitlines():
        line = _strip_md(raw_line).strip()
        if not line:
            continue
        m = _SPEAKER_RE.match(line)
        if m:
            speaker_name = m.group(1).strip()
            body = m.group(2).strip()
        else:
            speaker_name = None
            body = line
        i += 1
        segments.append(
            {
                "segment_id": f"seg_{i:03d}",
                "speaker_id": assign(speaker_name),
                "speaker_name": speaker_name,
                "start_ms": None,
                "end_ms": None,
                "text": body,
                "confidence": None,
                "is_final": True,
            }
        )
    return segments
