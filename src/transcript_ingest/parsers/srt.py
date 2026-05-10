"""SRT parser — uses the `srt` library; speaker extracted from `Name: text` prefix."""
from __future__ import annotations

import re

import srt as _srt

from ._speakers import make_speaker_registry

_SPEAKER_RE = re.compile(r"^([A-Z][a-zA-Z0-9 _.'-]{0,40}):\s*(.*)$", re.DOTALL)


def parse_srt(text: str) -> list[dict]:
    subs = list(_srt.parse(text))
    assign = make_speaker_registry()
    segments: list[dict] = []
    for i, sub in enumerate(subs, start=1):
        m = _SPEAKER_RE.match(sub.content.strip())
        if m:
            speaker_name = m.group(1).strip()
            body = m.group(2).strip()
        else:
            speaker_name = None
            body = sub.content.strip()
        segments.append(
            {
                "segment_id": f"seg_{i:03d}",
                "speaker_id": assign(speaker_name),
                "speaker_name": speaker_name,
                "start_ms": int(sub.start.total_seconds() * 1000),
                "end_ms": int(sub.end.total_seconds() * 1000),
                "text": body,
                "confidence": None,
                "is_final": True,
            }
        )
    return segments
