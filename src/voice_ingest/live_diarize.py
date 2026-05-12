"""Per-meeting rolling-window diarizer for the Wave 8 live pipeline.

Holds a 30-s rolling buffer of decoded PCM (float32, mono, 16 kHz) per
meeting and answers "who spoke during [t0_ms, t1_ms]?" by re-running the
existing pyannote pipeline (`voice_ingest.diarize._get_pipeline`) on the
buffered audio. The answer is a stable speaker label (`speaker_1`,
`speaker_2`, ...) the gate consumer can attach to a `CompleteSentence`
before persisting it.

Wave 8.5 will gate persistence on `assign(...)` returning non-None or
`DIARIZATION_GATE_TIMEOUT_MS` elapsing. This module knows nothing about
the gate — its only job is "given a window and a buffer, return the
dominant speaker label."

Audio buffering is performed by the storage-router caller (live_route)
via `librosa.load(temp_path, sr=16000, mono=True)` after the chunk has
been transcribed but before the temp .webm is deleted. The decoded PCM
is appended via `append_audio()` along with the chunk's timeline
[t0_ms, t1_ms] anchor. Stale chunks (older than the rolling window) are
trimmed on every append.
"""

from __future__ import annotations

import logging
from collections import deque
from dataclasses import dataclass, field

import numpy as np

log = logging.getLogger(__name__)

# Rolling window length. 30 s is enough for pyannote to settle a label
# but small enough that a single CPU re-run completes inside the live
# chunk cadence on a GPU host. CPU-only deploys will fall back to
# single-speaker (the existing batch-path graceful degradation).
ROLLING_WINDOW_MS = 30_000

# 16 kHz mono float32 = 64 KB/s; 30-s buffer ≈ 1.92 MB per meeting.
SAMPLE_RATE = 16_000


@dataclass
class _AudioFrame:
    t0_ms: int
    t1_ms: int
    pcm: np.ndarray  # float32, mono, 16 kHz


@dataclass
class LiveDiarizer:
    """Per-meeting rolling-window diarizer. Construct one instance per
    live meeting and feed it audio frames as they arrive."""

    meeting_id: str
    rolling_window_ms: int = ROLLING_WINDOW_MS
    _frames: deque[_AudioFrame] = field(default_factory=deque)
    # Stable rename map: pyannote labels (e.g. `SPEAKER_00`) -> our IDs
    # (`speaker_1`). First-seen-wins so renumbering is stable across
    # re-runs of the pipeline within one meeting.
    _label_map: dict[str, str] = field(default_factory=dict)

    def append_audio(self, t0_ms: int, t1_ms: int, pcm: np.ndarray) -> None:
        """Append a chunk's decoded PCM and trim stale frames.

        `pcm` MUST be float32 mono at `SAMPLE_RATE`. Caller (live_route)
        is responsible for `librosa.load(path, sr=16000, mono=True)`.
        """
        self._frames.append(_AudioFrame(t0_ms=t0_ms, t1_ms=t1_ms, pcm=pcm))
        self._trim_stale()

    def assign(self, t0_ms: int, t1_ms: int) -> str | None:
        """Return the dominant speaker label for the window `[t0_ms, t1_ms]`.

        Returns None if the buffered window does not yet cover `t1_ms`,
        signalling the gate consumer to wait or time out. Returns a stable
        `speaker_N` string otherwise. Pyannote is invoked synchronously;
        callers must run this off the event loop (run_in_executor) if
        they care about latency — Wave 8.5's gate consumer does so.
        """
        if not self._frames or self._frames[-1].t1_ms < t1_ms:
            return None
        try:
            return self._run_pyannote(t0_ms, t1_ms)
        except Exception as exc:  # noqa: BLE001 — pyannote / GPU OOM
            log.warning(
                "live_diarize: pyannote failed for meeting=%s [%s,%s]: %s",
                self.meeting_id,
                t0_ms,
                t1_ms,
                exc,
            )
            return None

    # --- internals -----------------------------------------------------

    def _trim_stale(self) -> None:
        if not self._frames:
            return
        cutoff = self._frames[-1].t1_ms - self.rolling_window_ms
        while self._frames and self._frames[0].t1_ms < cutoff:
            self._frames.popleft()

    def _run_pyannote(self, t0_ms: int, t1_ms: int) -> str | None:
        """Run pyannote on the concatenated buffer; return the label that
        spoke for the largest fraction of `[t0_ms, t1_ms]`.

        Stub-friendly: the pyannote pipeline is imported lazily inside
        this method so unit tests can monkeypatch the whole method
        without paying the import cost.
        """
        from voice_ingest.diarize import _get_pipeline  # lazy

        if not self._frames:
            return None
        pcm = np.concatenate([f.pcm for f in self._frames])
        # Pyannote accepts a (waveform, sample_rate) dict.
        pipeline = _get_pipeline()
        diarization = pipeline({"waveform": pcm[None, :], "sample_rate": SAMPLE_RATE})

        # Convert the requested window onto the buffer-relative timeline:
        # the buffer's leftmost sample corresponds to `_frames[0].t0_ms`.
        anchor_ms = self._frames[0].t0_ms
        rel_t0 = max(0, t0_ms - anchor_ms) / 1000.0
        rel_t1 = max(rel_t0, t1_ms - anchor_ms) / 1000.0

        # Sum the per-label time inside [rel_t0, rel_t1]; pick the max.
        per_label_time: dict[str, float] = {}
        for turn, _track, label in diarization.itertracks(yield_label=True):
            overlap_lo = max(turn.start, rel_t0)
            overlap_hi = min(turn.end, rel_t1)
            if overlap_hi <= overlap_lo:
                continue
            per_label_time[label] = per_label_time.get(label, 0.0) + (
                overlap_hi - overlap_lo
            )
        if not per_label_time:
            return None
        winner = max(per_label_time, key=per_label_time.get)
        return self._stable_label(winner)

    def _stable_label(self, raw: str) -> str:
        """Map a raw pyannote label to a stable `speaker_N` ID.

        Stability is per-meeting; the first new pyannote label seen gets
        `speaker_1`, the second `speaker_2`, etc. Subsequent re-runs of
        the pipeline that reuse the same raw label keep the same ID.
        """
        if raw not in self._label_map:
            self._label_map[raw] = f"speaker_{len(self._label_map) + 1}"
        return self._label_map[raw]


__all__ = [
    "LiveDiarizer",
    "ROLLING_WINDOW_MS",
    "SAMPLE_RATE",
]
