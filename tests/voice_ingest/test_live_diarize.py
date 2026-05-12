"""Wave 8.4 — LiveDiarizer unit tests with mocked pyannote.

These tests never instantiate the real pipeline. They patch
`LiveDiarizer._run_pyannote` (or the pipeline factory inside it) so the
math around buffer trimming, label-stability, and window-overlap is
verifiable without a HF token, GPU, or audio file.
"""

from __future__ import annotations

import numpy as np
import pytest

from voice_ingest.live_diarize import (
    ROLLING_WINDOW_MS,
    SAMPLE_RATE,
    LiveDiarizer,
)


def _silence(seconds: float) -> np.ndarray:
    return np.zeros(int(seconds * SAMPLE_RATE), dtype=np.float32)


def test_assign_returns_none_when_buffer_does_not_cover_window():
    diar = LiveDiarizer(meeting_id="m_test")
    diar.append_audio(0, 5_000, _silence(5.0))
    # Window extends past buffered tail.
    assert diar.assign(0, 10_000) is None


def test_assign_returns_stable_label_via_mocked_pipeline(monkeypatch):
    diar = LiveDiarizer(meeting_id="m_test")
    diar.append_audio(0, 10_000, _silence(10.0))

    # Replace `_run_pyannote` with a fixed return; we are testing the
    # outer assign() contract here, not the pyannote integration.
    monkeypatch.setattr(
        diar, "_run_pyannote", lambda t0, t1: diar._stable_label("SPEAKER_00")
    )
    label = diar.assign(0, 5_000)
    assert label == "speaker_1"


def test_label_stability_across_calls():
    diar = LiveDiarizer(meeting_id="m_test")
    # First-seen pyannote label `SPEAKER_03` is mapped to `speaker_1`;
    # subsequent calls with the same raw label return the same ID.
    assert diar._stable_label("SPEAKER_03") == "speaker_1"
    assert diar._stable_label("SPEAKER_07") == "speaker_2"
    assert diar._stable_label("SPEAKER_03") == "speaker_1"
    assert diar._stable_label("SPEAKER_07") == "speaker_2"


def test_buffer_trims_stale_frames_beyond_rolling_window():
    diar = LiveDiarizer(meeting_id="m_test", rolling_window_ms=10_000)
    # Append 5 chunks each 5 s long with monotonic timestamps.
    for i in range(5):
        diar.append_audio(i * 5_000, (i + 1) * 5_000, _silence(5.0))
    # Latest chunk ends at 25_000; window=10_000 → cutoff=15_000.
    # Only frames whose t1_ms >= 15_000 survive: chunks ending at
    # 15_000, 20_000, 25_000 (3 frames).
    assert len(diar._frames) == 3
    assert diar._frames[0].t0_ms == 10_000


def test_assign_picks_label_with_largest_overlap_in_window(monkeypatch):
    """End-to-end-ish: stub pyannote with a fake diarization that has two
    overlapping labels in the requested window; assert assign picks the
    one with the larger overlap."""
    diar = LiveDiarizer(meeting_id="m_test")
    diar.append_audio(0, 10_000, _silence(10.0))

    class _FakeTurn:
        def __init__(self, start: float, end: float) -> None:
            self.start = start
            self.end = end

    class _FakeDiarization:
        def itertracks(self, yield_label: bool = True):
            # SPEAKER_A: 0.0–3.0 (3.0 s in window 0–5)
            # SPEAKER_B: 3.0–9.0 (overlap with 0–5 is 2.0 s)
            yield (_FakeTurn(0.0, 3.0), None, "SPEAKER_A")
            yield (_FakeTurn(3.0, 9.0), None, "SPEAKER_B")

    class _FakePipeline:
        def __call__(self, _audio):
            return _FakeDiarization()

    monkeypatch.setattr(
        "voice_ingest.diarize._get_pipeline", lambda: _FakePipeline()
    )
    label = diar.assign(0, 5_000)
    # SPEAKER_A wins with 3.0 s vs SPEAKER_B's 2.0 s in the window.
    assert label == "speaker_1"
    assert diar._stable_label("SPEAKER_A") == "speaker_1"


def test_assign_returns_none_on_pyannote_exception(monkeypatch):
    diar = LiveDiarizer(meeting_id="m_test")
    diar.append_audio(0, 5_000, _silence(5.0))

    def _raise(t0, t1):
        raise RuntimeError("pyannote OOM")

    monkeypatch.setattr(diar, "_run_pyannote", _raise)
    assert diar.assign(0, 5_000) is None
