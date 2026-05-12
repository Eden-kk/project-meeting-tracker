"""Core voice-file transcription.

Public surface: `transcribe_voice_file(path) -> NormalizedTranscript dict`.
"""

from __future__ import annotations

import logging
from math import exp
from pathlib import Path
from uuid import uuid4

from faster_whisper import WhisperModel

from . import config, schema
from .diarize import assign_speakers

log = logging.getLogger(__name__)

_model: WhisperModel | None = None


def _get_model() -> WhisperModel:
    global _model
    if _model is None:
        _model = WhisperModel(
            config.WHISPER_MODEL,
            device=config.WHISPER_DEVICE,
            compute_type=config.WHISPER_COMPUTE_TYPE,
            download_root=str(config.MODEL_CACHE_DIR),
        )
    return _model


def _confidence(avg_logprob: float | None) -> float | None:
    if avg_logprob is None:
        return None
    # Heuristic: exp(avg_logprob) lands in (0,1] for negative log-probs.
    # Not a calibrated probability; kept for downstream sorting only.
    return max(0.0, min(1.0, exp(avg_logprob)))


def transcribe_voice_file(
    audio_path: str | Path,
    *,
    meeting_id: str | None = None,
) -> dict:
    """Transcribe an audio file and return a NormalizedTranscript dict."""
    path = str(audio_path)
    model = _get_model()
    segments_iter, _info = model.transcribe(
        path,
        language=None,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,
        condition_on_previous_text=True,
    )

    segments: list[dict] = []
    for i, seg in enumerate(segments_iter):
        segments.append({
            "segment_id": f"seg_{i:03d}",
            "speaker_id": "speaker_1",
            "speaker_name": None,
            "start_ms": int(seg.start * 1000),
            "end_ms": int(seg.end * 1000),
            "text": seg.text.strip(),
            "confidence": _confidence(seg.avg_logprob),
            "source_type": "voice_file",
            "is_final": True,
        })

    try:
        segments = assign_speakers(path, segments)
    except Exception as exc:
        log.warning("diarization failed, single-speaker fallback: %s", exc)

    result = {
        "meeting_id": meeting_id or f"m_{uuid4().hex[:12]}",
        "segments": segments,
    }
    schema.validate(result)
    return result


__all__ = ["transcribe_voice_file"]
