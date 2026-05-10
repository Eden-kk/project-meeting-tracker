# Worktree C — transcript-ingest

## Owns

The text-transcript ingestion path. Takes an uploaded transcript file or
pasted text, detects the format, parses it, emits a `NormalizedTranscript`.

Tech:
- Python 3.12 + FastAPI (handler/service)
- webvtt-py for VTT, srt for SRT, plain regex for txt/md/json

## Consumes (from worktree A, branch `phase1/contracts`)

- `schemas/normalized_transcript.schema.json`
- `schemas/speaker_segment.schema.json`
- `fixtures/sample_transcript.txt`
- `fixtures/sample_transcript.vtt`
- `fixtures/sample_transcript.srt`
- `fixtures/expected_normalized.json` (golden output — VTT path should match exactly)

## Supported formats (per design-doc §11.2)

```
txt  — plain text, may have "Speaker: text" lines, no timestamps
md   — same as txt but markdown-formatted
vtt  — WebVTT with cue timings; speaker tags via <v Name>
srt  — SubRip with cue timings; speaker tags as "Name: text" prefix
json — structured input (schema TBD; treat as pre-normalized for now)
```

## Lane boundaries — DO NOT touch

- `worktrees/voice-ingest/` — that's worktree B
- `worktrees/storage-router/` — DB + status state machine are D's
- `worktrees/frontend/` — UI is E

This worktree exposes a single function:
`parse_transcript(payload, format_hint=None) -> NormalizedTranscript`.
Worktree D calls it. That's the only contract surface.

## First build task

**Do not start before worktree A is merged.**

```text
1. Create venv + install: pip install fastapi webvtt-py srt
2. Implement format detection from filename extension + content sniffing
3. Implement parsers per format
4. Round-trip pytest: sample_transcript.vtt → matches expected_normalized.json
5. Round-trip pytest: sample_transcript.srt → segments match (ms-level)
6. Round-trip pytest: sample_transcript.txt → segments produced (timestamps null)
```
