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

        # pyannote.audio 3.x's `Pipeline.from_pretrained` takes the auth token
        # as `use_auth_token`, NOT `token` (the latter raises "unexpected
        # keyword argument 'token'" and silently drops us into single-speaker
        # fallback — the bug that made every meeting show only speaker_1).
        # Try the correct kwarg first, fall back across versions.
        try:
            _pipeline = Pipeline.from_pretrained(
                config.PYANNOTE_PIPELINE,
                use_auth_token=config.HF_TOKEN,
            )
        except TypeError:
            _pipeline = Pipeline.from_pretrained(
                config.PYANNOTE_PIPELINE,
                token=config.HF_TOKEN,
            )
    return _pipeline


def assign_speakers(
    audio_path: str,
    segments: list[dict],
    *,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> list[dict]:
    """Overlay pyannote speaker labels on whisper segments.

    `num_speakers` (exact count) or `min_speakers`/`max_speakers` (range) are
    forwarded to pyannote when the caller knows the speaker count. Pyannote's
    default auto-clustering can under-count on short recordings, similar
    voices, or heavy code-switching — the hint forces a specific cluster
    count and dramatically improves accuracy when the count is known.
    """
    if not config.HF_TOKEN:
        log.warning("HF_TOKEN unset; skipping diarization (single-speaker fallback)")
        return list(segments)

    pipeline = _get_pipeline()
    pipeline_kwargs: dict = {}
    if num_speakers is not None:
        pipeline_kwargs["num_speakers"] = int(num_speakers)
    if min_speakers is not None:
        pipeline_kwargs["min_speakers"] = int(min_speakers)
    if max_speakers is not None:
        pipeline_kwargs["max_speakers"] = int(max_speakers)
    diarization = pipeline(audio_path, **pipeline_kwargs)

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
