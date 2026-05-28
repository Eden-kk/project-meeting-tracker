"""DeepInfra-hosted Whisper-large-v3 ASR backend.

Replaces the self-hosted faster-whisper transcription step with a call to
DeepInfra's OpenAI-compatible ``/audio/transcriptions`` endpoint. This is
ASR ONLY — DeepInfra does not return speaker labels — so the caller still
runs pyannote ``assign_speakers`` over the same audio file to overlay
diarization. The output shape mirrors what the faster-whisper path emits
so the rest of the pipeline is unchanged.

Selected via ``ASR_BACKEND=deepinfra`` + ``DEEPINFRA_API_KEY``.
"""

from __future__ import annotations

import logging
from math import exp
from pathlib import Path

import httpx

from . import config

log = logging.getLogger(__name__)


def _confidence(avg_logprob: float | None) -> float | None:
    if avg_logprob is None:
        return None
    return max(0.0, min(1.0, exp(avg_logprob)))


def transcribe_deepinfra(audio_path: str) -> list[dict]:
    """POST the audio to DeepInfra Whisper and return normalized segments.

    Returns a list of segment dicts in the same shape the faster-whisper
    path produces (minus the speaker overlay, which the caller adds). Each:
        {segment_id, speaker_id, speaker_name, start_ms, end_ms, text,
         confidence, source_type, is_final}

    Raises RuntimeError on a missing key or a non-2xx response so the
    caller can surface it the same way a local-model failure would.
    """
    if not config.DEEPINFRA_API_KEY:
        raise RuntimeError(
            "ASR_BACKEND=deepinfra but DEEPINFRA_API_KEY is unset"
        )

    with open(audio_path, "rb") as f:
        files = {"file": (Path(audio_path).name, f, "application/octet-stream")}
        data = {
            "model": config.DEEPINFRA_ASR_MODEL,
            "response_format": "verbose_json",
        }
        resp = httpx.post(
            config.DEEPINFRA_ASR_URL,
            headers={"Authorization": f"Bearer {config.DEEPINFRA_API_KEY}"},
            files=files,
            data=data,
            timeout=config.DEEPINFRA_ASR_TIMEOUT_S,
        )
    if resp.status_code >= 400:
        raise RuntimeError(
            f"DeepInfra ASR returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()

    raw_segments = payload.get("segments") or []
    segments: list[dict] = []
    for i, seg in enumerate(raw_segments):
        text = (seg.get("text") or "").strip()
        if not text:
            continue
        start = float(seg.get("start") or 0.0)
        end = float(seg.get("end") or start)
        segments.append({
            "segment_id": f"seg_{i:03d}",
            "speaker_id": "speaker_1",
            "speaker_name": None,
            "start_ms": int(start * 1000),
            "end_ms": int(end * 1000),
            "text": text,
            "confidence": _confidence(seg.get("avg_logprob")),
            "source_type": "voice_file",
            "is_final": True,
        })

    # Some short clips come back with `text` but an empty `segments` list.
    # Fall back to a single whole-clip segment so we never drop real speech.
    if not segments:
        whole = (payload.get("text") or "").strip()
        if whole:
            duration = float(payload.get("duration") or 0.0)
            segments.append({
                "segment_id": "seg_000",
                "speaker_id": "speaker_1",
                "speaker_name": None,
                "start_ms": 0,
                "end_ms": int(duration * 1000),
                "text": whole,
                "confidence": _confidence(payload.get("avg_logprob")),
                "source_type": "voice_file",
                "is_final": True,
            })

    log.info("deepinfra ASR: %d segments from %s", len(segments), Path(audio_path).name)
    return segments


__all__ = ["transcribe_deepinfra"]
