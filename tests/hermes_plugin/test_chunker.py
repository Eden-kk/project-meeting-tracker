"""Unit tests for the time-windowed transcript chunker."""

from __future__ import annotations

import pytest

from hermes_plugin.chunker import Chunk, chunk_segments


def _seg(seg_id: str, start_ms: int | None, end_ms: int | None, speaker: str | None = "A", text: str = "x") -> dict:
    return {
        "segment_id": seg_id,
        "text": text,
        "speaker_name": speaker,
        "start_ms": start_ms,
        "end_ms": end_ms,
    }


# 1. 30-min transcript with 5-min windows → 6 chunks
def test_30min_with_5min_windows_yields_6_chunks() -> None:
    segs: list[dict] = []
    # one segment per minute, 30 minutes total → 30 segments → 6 chunks of 5
    for minute in range(30):
        start = minute * 60_000
        segs.append(_seg(f"seg_{minute:03d}", start, start + 30_000))

    chunks = chunk_segments(segs, chunk_minutes=5)
    assert len(chunks) == 6
    assert [c.index for c in chunks] == [0, 1, 2, 3, 4, 5]
    # Each chunk should have 5 segments (one per minute, 5 min/window).
    for c in chunks:
        assert len(c.segments) == 5


# 2. Sparse meeting → empty windows dropped
def test_sparse_meeting_drops_empty_windows() -> None:
    # Two segments 30 min apart: minute 0 and minute 30. With 5-min windows
    # there should be exactly 2 chunks (no empty ones in between).
    segs = [
        _seg("seg_001", 0, 5_000),
        _seg("seg_002", 30 * 60_000, 30 * 60_000 + 5_000),
    ]
    chunks = chunk_segments(segs, chunk_minutes=5)
    assert len(chunks) == 2
    assert chunks[0].index == 0
    assert chunks[1].index == 1
    assert chunks[0].segments[0]["segment_id"] == "seg_001"
    assert chunks[1].segments[0]["segment_id"] == "seg_002"


# 3. Single short segment → 1 chunk
def test_single_segment_under_window_yields_one_chunk() -> None:
    segs = [_seg("seg_001", 0, 60_000)]
    chunks = chunk_segments(segs, chunk_minutes=5)
    assert len(chunks) == 1
    assert chunks[0].segments == segs
    assert chunks[0].start_ms == 0


# 4. Untimestamped → 1 chunk regardless of chunk_minutes
def test_untimestamped_segments_collapse_to_one_chunk() -> None:
    segs = [
        _seg("seg_001", None, None),
        _seg("seg_002", None, None),
        _seg("seg_003", None, None),
    ]
    chunks = chunk_segments(segs, chunk_minutes=5)
    assert len(chunks) == 1
    assert chunks[0].segments == segs
    assert chunks[0].start_ms is None
    assert chunks[0].end_ms is None

    # Same result for chunk_minutes=1
    chunks2 = chunk_segments(segs, chunk_minutes=1)
    assert len(chunks2) == 1


# 5. Boundary-crossing segment assigned to its start_ms window
def test_boundary_crossing_segment_assigned_to_start_window() -> None:
    # 5-min window = 300_000 ms boundary. Segment starts at 290_000 (window 0)
    # and ends at 320_000 (would be window 1 by end_ms). It belongs to window 0.
    segs = [
        _seg("seg_a", 100_000, 200_000),  # window 0
        _seg("seg_cross", 290_000, 320_000),  # window 0 (start_ms)
        _seg("seg_b", 360_000, 400_000),  # window 1
    ]
    chunks = chunk_segments(segs, chunk_minutes=5)
    assert len(chunks) == 2
    assert [s["segment_id"] for s in chunks[0].segments] == ["seg_a", "seg_cross"]
    assert [s["segment_id"] for s in chunks[1].segments] == ["seg_b"]


# 6. chunk_minutes=1 on a 10-min meeting → 10 chunks
def test_chunk_minutes_1_on_10min_meeting_yields_10_chunks() -> None:
    segs = [_seg(f"seg_{i:03d}", i * 60_000, i * 60_000 + 30_000) for i in range(10)]
    chunks = chunk_segments(segs, chunk_minutes=1)
    assert len(chunks) == 10
    for i, c in enumerate(chunks):
        assert len(c.segments) == 1
        assert c.segments[0]["segment_id"] == f"seg_{i:03d}"


# 7. Empty segments list → empty chunks list
def test_empty_segments_yields_empty_chunks() -> None:
    assert chunk_segments([], chunk_minutes=5) == []


# 8. Speakers per chunk are deduped
def test_speakers_collected_and_deduped_per_chunk() -> None:
    segs = [
        _seg("seg_001", 0, 1_000, speaker="Alice"),
        _seg("seg_002", 30_000, 31_000, speaker="Bob"),
        _seg("seg_003", 60_000, 61_000, speaker="Alice"),  # dup in same window
        _seg("seg_004", 6 * 60_000, 6 * 60_000 + 1_000, speaker="Carol"),  # next window
    ]
    chunks = chunk_segments(segs, chunk_minutes=5)
    assert len(chunks) == 2
    assert chunks[0].speakers == ["Alice", "Bob"]
    assert chunks[1].speakers == ["Carol"]


def test_chunk_minutes_zero_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_segments([_seg("s", 0, 1)], chunk_minutes=0)


def test_chunk_dataclass_returned() -> None:
    """Sanity: the returned objects are real Chunk instances."""
    chunks = chunk_segments([_seg("s", 0, 1)], chunk_minutes=5)
    assert isinstance(chunks[0], Chunk)
