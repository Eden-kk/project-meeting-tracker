"""Core voice-file transcription.

Public surface: `transcribe_voice_file(path) -> NormalizedTranscript dict`.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from math import exp
from pathlib import Path
from uuid import uuid4

from faster_whisper import WhisperModel

from . import config, schema
from .diarize import assign_speakers

_VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov"}

log = logging.getLogger(__name__)

# Known faster-whisper hallucinations on low-speech / silent audio. Whisper
# (especially on Chinese) emits canned YouTube-outro / subtitle-credit text
# when there is no real speech, and can also echo back the `initial_prompt`.
# These contaminate live per-chunk transcription badly (each 10s chunk is
# decoded in isolation, so quiet chunks reliably trigger them). We drop any
# segment whose text matches one of these substrings, or which echoes the
# initial prompt. See live-mode diagnosis 2026-05-22.
_HALLUCINATION_SUBSTRINGS = (
    "请不吝点赞",
    "点赞 订阅",
    "点赞、订阅",
    "订阅 转发",
    "打赏支持明镜",
    "明镜与点点栏目",
    "明镜需要您的支持",
    "字幕由",
    "字幕志愿者",
    "感谢观看",
    "谢谢观看",
    "谢谢大家观看",
    "請不吝點贊",  # traditional variants
    "點贊 訂閱",
    "訂閱 轉發",
)


def _norm_cjk(s: str) -> str:
    """Lowercase + strip whitespace/punctuation for fuzzy compare."""
    return "".join(ch for ch in s.lower() if ch.strip() and ch not in "，。、,. !！?？")


def _longest_common_substr_len(a: str, b: str) -> int:
    """Length of the longest contiguous substring shared by a and b."""
    if not a or not b:
        return 0
    prev = [0] * (len(b) + 1)
    best = 0
    for i in range(1, len(a) + 1):
        cur = [0] * (len(b) + 1)
        ai = a[i - 1]
        for j in range(1, len(b) + 1):
            if ai == b[j - 1]:
                cur[j] = prev[j - 1] + 1
                if cur[j] > best:
                    best = cur[j]
        prev = cur
    return best


# A segment sharing this many contiguous chars with the initial prompt is
# treated as a prompt-echo hallucination. The real prompt fragment that
# leaks ("会议录音的中英文混合转录") is ~12 chars; genuine speech almost never
# shares an 8-char contiguous run with the prompt.
_PROMPT_ECHO_MIN_RUN = 8


def _is_hallucination(text: str, initial_prompt: str | None) -> bool:
    """True if a transcribed segment looks like a Whisper hallucination.

    Two checks: (1) it contains a known canned-junk substring; (2) it shares
    a long contiguous run with the initial prompt (Whisper regurgitates the
    prompt — verbatim or with a swapped prefix like 以下→并且/那段 — on empty
    audio).
    """
    t = (text or "").strip()
    if not t:
        return False
    for junk in _HALLUCINATION_SUBSTRINGS:
        if junk in t:
            return True
    if initial_prompt:
        nt, npmt = _norm_cjk(t), _norm_cjk(initial_prompt)
        if nt and _longest_common_substr_len(nt, npmt) >= _PROMPT_ECHO_MIN_RUN:
            return True
    return False

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


def _extract_audio_track(video_path: str) -> str:
    """Strip a video container down to a 16-kHz mono WAV via ffmpeg.

    Returned path lives in tempdir owned by the caller — we don't try to
    clean it up here because faster-whisper and pyannote both stream the
    file lazily during transcribe; the request handler tears down its
    tempdir at the end of the request.
    """
    if not shutil.which("ffmpeg"):
        raise RuntimeError(
            "ffmpeg not found on PATH; cannot extract audio from video container"
        )
    out_path = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    proc = subprocess.run(
        [
            "ffmpeg", "-y", "-loglevel", "error",
            "-i", video_path,
            "-vn",                  # drop video stream
            "-ac", "1",             # mono
            "-ar", "16000",         # 16 kHz (whisper-native)
            "-f", "wav",
            out_path,
        ],
        capture_output=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"ffmpeg failed to extract audio: {stderr or 'unknown error'}")
    return out_path


def _transcribe_faster_whisper(path: str) -> list[dict]:
    """Self-hosted CTranslate2 Whisper ASR. Returns normalized segments
    (speaker overlay is added later by assign_speakers)."""
    model = _get_model()
    segments_iter, _info = model.transcribe(
        path,
        language=None,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 500},
        word_timestamps=False,
        condition_on_previous_text=False,
        initial_prompt=config.WHISPER_INITIAL_PROMPT,
        beam_size=5,
        temperature=[0.0, 0.2, 0.4, 0.6],
        no_speech_threshold=0.6,
        log_prob_threshold=-1.0,
        compression_ratio_threshold=2.4,
    )
    segments: list[dict] = []
    idx = 0
    for seg in segments_iter:
        text = seg.text.strip()
        if _is_hallucination(text, config.WHISPER_INITIAL_PROMPT):
            log.info("dropping hallucinated segment: %r", text[:60])
            continue
        segments.append({
            "segment_id": f"seg_{idx:03d}",
            "speaker_id": "speaker_1",
            "speaker_name": None,
            "start_ms": int(seg.start * 1000),
            "end_ms": int(seg.end * 1000),
            "text": text,
            "confidence": _confidence(seg.avg_logprob),
            "source_type": "voice_file",
            "is_final": True,
        })
        idx += 1
    return segments


def transcribe_voice_file(
    audio_path: str | Path,
    *,
    meeting_id: str | None = None,
    num_speakers: int | None = None,
    min_speakers: int | None = None,
    max_speakers: int | None = None,
) -> dict:
    """Transcribe an audio file and return a NormalizedTranscript dict.

    If `audio_path` points to a video container (.mp4/.m4v/.mov), the audio
    track is extracted to a temporary WAV first so both faster-whisper and
    pyannote diarization see a clean PCM stream — pyannote's torchaudio
    backend is unreliable on mp4 muxed files.

    `num_speakers` (exact) or `min_speakers`/`max_speakers` (range) are
    forwarded to pyannote. Pyannote's auto-cluster under-counts on short or
    code-switched recordings; supplying the known speaker count is the most
    effective accuracy lever the API exposes.
    """
    path = str(audio_path)
    extracted_wav: str | None = None
    if Path(path).suffix.lower() in _VIDEO_SUFFIXES:
        log.info("video container detected (%s); extracting audio track", Path(path).suffix)
        extracted_wav = _extract_audio_track(path)
        path = extracted_wav
    if config.ASR_BACKEND == "deepinfra":
        from .deepinfra_asr import transcribe_deepinfra

        segments = transcribe_deepinfra(path)
    else:
        segments = _transcribe_faster_whisper(path)

    diarization_error: str | None = None
    try:
        segments = assign_speakers(
            path, segments,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except Exception as exc:
        diarization_error = f"{type(exc).__name__}: {exc}"
        log.warning("diarization failed, single-speaker fallback: %s", diarization_error)

    result = {
        "meeting_id": meeting_id or f"m_{uuid4().hex[:12]}",
        "segments": segments,
    }
    schema.validate(result)
    if extracted_wav is not None:
        try:
            Path(extracted_wav).unlink()
        except OSError:
            pass
    return result


__all__ = ["transcribe_voice_file"]
