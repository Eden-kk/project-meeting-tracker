"""Speaker diarization layer (pyannote-audio).

`assign_speakers(audio_path, segments)` overlays diarization onto a list of
transcript segments, returning a new list with `speaker_id` reassigned. Falls
back to single-speaker output (every segment keeps `speaker_1`) when
`HF_TOKEN` is unset — the documented graceful-degradation path.
"""

from __future__ import annotations

import logging
from copy import deepcopy

from . import config

log = logging.getLogger(__name__)

_pipeline = None


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        from pyannote.audio import Pipeline

        _pipeline = Pipeline.from_pretrained(
            config.PYANNOTE_PIPELINE,
            token=config.HF_TOKEN,
        )
    return _pipeline


def assign_speakers(audio_path: str, segments: list[dict]) -> list[dict]:
    if not config.HF_TOKEN:
        log.warning("HF_TOKEN unset; skipping diarization (single-speaker fallback)")
        return list(segments)

    pipeline = _get_pipeline()
    diarization = pipeline(audio_path)

    # Collect (start_s, end_s, raw_label) and assign stable speaker_N ids by
    # first appearance.
    turns: list[tuple[float, float, str]] = []
    label_map: dict[str, str] = {}
    for turn, _, label in diarization.itertracks(yield_label=True):
        if label not in label_map:
            label_map[label] = f"speaker_{len(label_map) + 1}"
        turns.append((turn.start, turn.end, label_map[label]))

    out = deepcopy(segments)
    for seg in out:
        s = (seg["start_ms"] or 0) / 1000.0
        e = (seg["end_ms"] or 0) / 1000.0
        best_overlap = 0.0
        best_label: str | None = None
        for ts, te, lab in turns:
            overlap = max(0.0, min(te, e) - max(ts, s))
            if overlap > best_overlap:
                best_overlap = overlap
                best_label = lab
        if best_label is not None:
            seg["speaker_id"] = best_label
    return out


__all__ = ["assign_speakers"]
