# Worktree B — voice-ingest

## Owns

The voice-file ingestion path. Takes uploaded audio, runs STT + diarization,
emits a `NormalizedTranscript` (schema in worktree A).

Tech:
- Python 3.12 + FastAPI (handler/service)
- Local Whisper for STT (Chinese + English multilingual)
- pyannote-audio (or whisperx) for diarization

## Consumes (from worktree A, branch `phase1/contracts`)

- `schemas/normalized_transcript.schema.json`
- `schemas/speaker_segment.schema.json`
- `fixtures/sample_audio.wav` (placeholder; **replace with a real bilingual sample** once Whisper is up)
- `fixtures/expected_normalized.json` (golden output for round-trip tests)

## Lane boundaries — DO NOT touch

- `worktrees/transcript-ingest/` — that's worktree C
- `worktrees/storage-router/` — DB writes, artifact persistence, status state machine all live there
- `worktrees/frontend/` — UI is worktree E

This worktree exposes a single in-process function (or HTTP endpoint, TBD
during implementation): `transcribe_voice_file(path) -> NormalizedTranscript`.
Worktree D calls it. That's the only contract surface.

## First build task — Whisper deployment

This is the first task of this worktree. **Do not start before worktree A is merged.**

```text
1. Create venv: python3 -m venv .venv && source .venv/bin/activate
2. Install: pip install faster-whisper pyannote-audio
3. Pick model:
   - Default: large-v3 (best Chinese + English; ~3GB; needs GPU for reasonable speed)
   - Fallback: medium (~1.5GB; CPU-tolerable for fixtures)
4. Run a smoke transcription on fixtures/sample_audio.wav once it's been
   replaced with real bilingual speech. The placeholder tone will obviously
   transcribe as nothing useful — generate a real sample first using e.g.:
     - record yourself saying one English sentence + one Chinese sentence
     - or use a TTS like Microsoft Edge TTS, or pyttsx3 with zh voice
5. Wire transcribe_voice_file() to return a NormalizedTranscript that
   validates against schemas/normalized_transcript.schema.json
6. Add diarization to assign speaker_id per segment
7. Add a pytest that round-trips: audio in → expected_normalized.json out
   (allow text similarity ≥ 0.85, exact equality is unrealistic)
```
