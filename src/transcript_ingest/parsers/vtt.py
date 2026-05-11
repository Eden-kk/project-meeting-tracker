"""VTT parser — uses webvtt-py and extracts `<v Name>` tags from raw caption text."""
from __future__ import annotations

import re

import webvtt

from ._speakers import make_speaker_registry

_TS_RE = re.compile(r"^(\d{2}):(\d{2}):(\d{2})[.,](\d{3})$")
_VTAG_RE = re.compile(r"<v\s+([^>]+)>")


def _ts_to_ms(ts: str) -> int:
    m = _TS_RE.match(ts.strip())
    if not m:
        raise ValueError(f"invalid VTT timestamp: {ts!r}")
    h, mi, s, ms = (int(x) for x in m.groups())
    return ((h * 3600) + (mi * 60) + s) * 1000 + ms


def parse_vtt(text: str) -> list[dict]:
    captions = list(webvtt.from_string(text))
    assign = make_speaker_registry()
    segments: list[dict] = []
    for i, cap in enumerate(captions, start=1):
        raw = getattr(cap, "raw_text", None) or cap.text
        m = _VTAG_RE.search(raw)
        speaker_name = m.group(1).strip() if m else None
        body = _VTAG_RE.sub("", raw).strip() if m else cap.text.strip()
        segments.append(
            {
                "segment_id": f"seg_{i:03d}",
                "speaker_id": assign(speaker_name),
                "speaker_name": speaker_name,
                "start_ms": _ts_to_ms(cap.start),
                "end_ms": _ts_to_ms(cap.end),
                "text": body,
                "confidence": None,
                "is_final": True,
            }
        )
    return segments
