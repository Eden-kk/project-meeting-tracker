# voice-ingest worktree (Phase 1, Worktree B)

Owns the voice-file ingestion path: given an uploaded audio file, run local
STT (faster-whisper) + speaker diarization (pyannote-audio) and emit a
`NormalizedTranscript` that conforms to `schemas/normalized_transcript.schema.json`.

See `SCOPE.md` for lane boundaries and `docs/design-doc.md` §11.1 for the
overall pipeline context.

## Contract surface

- In-process: `from src.voice_ingest import transcribe_voice_file`
- HTTP: `POST /voice/transcribe` (multipart upload), `GET /healthz`

This is the only surface other worktrees may consume.

## Setup

```bash
cd /home/yid042/projects/project-meeting-tracker/worktrees/voice-ingest
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# Pre-download the medium Whisper model (~1.5 GB):
python -c "from faster_whisper import WhisperModel; WhisperModel('medium', device='cpu', compute_type='int8', download_root='models')"
```

## Environment variables

| Var | Default | Notes |
|---|---|---|
| `WHISPER_MODEL` | `medium` | `large-v3` is the opt-in upgrade (better zh accuracy, ~3 GB, GPU recommended). |
| `WHISPER_DEVICE` | `auto` | `auto` resolves to `cuda` if available else `cpu`; explicit `cuda` / `cpu` accepted. |
| `WHISPER_COMPUTE_TYPE` | `int8` on cpu, `float16` on cuda | Override only if you know what you want. |
| `HF_TOKEN` | unset | Required for pyannote diarization. When unset, every segment falls back to `speaker_id="speaker_1"` (graceful degradation, see SCOPE.md). |
| `PYANNOTE_PIPELINE` | `pyannote/speaker-diarization-3.1` | Pinned. |
| `MODEL_CACHE_DIR` | `<worktree>/models/` | Gitignored. |
| `MAX_UPLOAD_BYTES` | `209715200` (200 MB) | FastAPI 413 guard. |

## Running tests

The bilingual round-trip test (`tests/test_voice_ingest.py`) needs `large-v3`
on a CUDA device — `medium` on CPU misidentifies the English half of the
Edge-TTS fixture as Chinese and fails the per-language similarity threshold.

```bash
source .venv/bin/activate
WHISPER_MODEL=large-v3 WHISPER_DEVICE=cuda WHISPER_COMPUTE_TYPE=float16 \
  pytest -xvs tests/
```

API tests run fine on the defaults (`medium`, cpu/int8).

## Running the HTTP server

```bash
source .venv/bin/activate
uvicorn src.voice_ingest.api:app --host 127.0.0.1 --port 8011
```
