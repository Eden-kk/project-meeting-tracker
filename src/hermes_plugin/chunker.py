"""Time-windowed chunking of normalized meeting transcripts.

The runtime calls :func:`chunk_segments` to slice a flat segment list
into fixed-duration windows by ``start_ms``. The downstream Claude
tool-use loop then runs once per chunk so long meetings don't blow the
context budget.

Design notes:
- ``Segment`` is a TypedDict matching the dict shape that
  ``hermes_plugin.tools.get_meeting_transcript`` returns. We do NOT
  reuse ``schemas.SpeakerSegment`` here because the runtime has been
  passing dicts all along; introducing a Pydantic dep at this seam
  would force every caller to validate twice.
- Chunk boundaries are time-based (``chunk_minutes * 60_000`` ms).
  A segment is assigned to the window its ``start_ms`` falls in even
  if its ``end_ms`` crosses into the next.
- If ANY segment lacks a ``start_ms``, we fall back to a single chunk
  containing every segment (degraded mode for fixtures and pasted
  transcripts that don't carry timestamps).
- Empty windows (silence between two distant segments) are dropped so
  the runtime doesn't waste a Claude call on nothing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, TypedDict


class Segment(TypedDict, total=False):
    """Subset of fields used by the chunker.

    Matches the dict that ``tools.get_meeting_transcript`` returns
    (which itself is a ``NormalizedTranscript.segments[i].model_dump``).
    Marked ``total=False`` so callers may pass dicts that include other
    keys (``confidence``, ``source_type``, ``is_final``) without typing
    complaints.
    """

    segment_id: str
    text: str
    speaker_name: Optional[str]
    start_ms: Optional[int]
    end_ms: Optional[int]


@dataclass
class Chunk:
    """One time-window of segments handed to a single Claude call."""

    index: int
    start_ms: Optional[int]
    end_ms: Optional[int]
    segments: list[dict] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)


def _has_all_timestamps(segments: list[dict]) -> bool:
    return all(s.get("start_ms") is not None for s in segments)


def _collect_speakers(segments: list[dict]) -> list[str]:
    """Return de-duped speaker names in first-seen order."""
    seen: dict[str, None] = {}
    for s in segments:
        name = s.get("speaker_name")
        if name and name not in seen:
            seen[name] = None
    return list(seen.keys())


def chunk_segments(
    segments: list[dict],
    chunk_minutes: int = 5,
) -> list[Chunk]:
    """Group ``segments`` into time-windowed chunks.

    Args:
        segments: Flat list of segment dicts, in transcript order.
        chunk_minutes: Window size in minutes (>=1).

    Returns:
        List of ``Chunk`` objects; empty list for empty input.
        Untimestamped input collapses to a single chunk with
        ``start_ms=end_ms=None``.
    """
    if chunk_minutes < 1:
        raise ValueError("chunk_minutes must be >= 1")
    if not segments:
        return []

    # Degraded mode: any missing start_ms → one chunk for the whole meeting.
    if not _has_all_timestamps(segments):
        return [
            Chunk(
                index=0,
                start_ms=None,
                end_ms=None,
                segments=list(segments),
                speakers=_collect_speakers(segments),
            )
        ]

    window_ms = chunk_minutes * 60_000
    # Bucket segments by their start_ms window index.
    buckets: dict[int, list[dict]] = {}
    for seg in segments:
        widx = int(seg["start_ms"]) // window_ms
        buckets.setdefault(widx, []).append(seg)

    chunks: list[Chunk] = []
    for out_idx, widx in enumerate(sorted(buckets)):
        bucket_segs = buckets[widx]
        # Use the bucket's actual segment range, not the abstract window
        # boundaries — the abstract boundaries can be misleading when a
        # window has only one short segment in it.
        seg_start = min(int(s["start_ms"]) for s in bucket_segs)
        seg_end_candidates = [
            int(s["end_ms"]) for s in bucket_segs if s.get("end_ms") is not None
        ]
        seg_end = max(seg_end_candidates) if seg_end_candidates else seg_start
        chunks.append(
            Chunk(
                index=out_idx,
                start_ms=seg_start,
                end_ms=seg_end,
                segments=bucket_segs,
                speakers=_collect_speakers(bucket_segs),
            )
        )
    return chunks


__all__ = ["Segment", "Chunk", "chunk_segments"]
