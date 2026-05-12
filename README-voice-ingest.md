# voice-ingest

Voice-file ingestion service for Tracker Phase 1, Worktree B. Takes uploaded audio (mp3/wav/m4a/webm/ogg), runs faster-whisper for STT (multilingual: English + Chinese) + pyannote-audio for diarization, and emits a `NormalizedTranscript` matching the contract schemas.

## Setup

Requires Python 3.12 + a CUDA GPU recommended (CPU works but is much slower for `large-v3`).

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run service

```bash
.venv/bin/uvicorn src.voice_ingest.api:app --host 127.0.0.1 --port 8021
```

## Run tests

```bash
WHISPER_MODEL=large-v3 WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16 \
  .venv/bin/pytest tests/voice_ingest/
```

(`medium` model on CPU mis-classifies bilingual audio as Chinese; `large-v3` on CUDA gets bilingual coverage.)

## HF token (optional, enables real diarization)

If `HF_TOKEN` is unset, the diarization layer falls back to assigning every segment to `speaker_1` (single-speaker stub).

## Whisper model defaults (Wave 8.2)

The default `WHISPER_MODEL` is `large-v3`. Notes:

- **Disk:** ~3 GB of weights cached under `MODEL_CACHE_DIR` (default `<repo>/models/`) on first use.
- **VRAM:** ~10 GB at `float16` (CUDA). On a CPU-only laptop the model will fall back to `int8` and run extremely slowly — override with `WHISPER_MODEL=medium` for local dev.
- **Code-switching:** `transcribe(...)` is invoked with `condition_on_previous_text=True` and `language=None` (auto-detect) so mid-utterance Chinese↔English code-switching transcribes in the spoken script rather than collapsing to a single language.
- **Cold start:** first request after a fresh deploy takes 60–90 s while weights download. The deploy image should pre-pull `large-v3` at build time to drop cold start to ~5 s.
