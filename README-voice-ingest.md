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
