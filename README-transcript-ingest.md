# transcript-ingest

Text-transcript ingestion service for Tracker Phase 1, Worktree C. Detects format of an uploaded transcript file (txt, md, vtt, srt, json) or pasted plain text, parses speakers and timestamps when present, and emits a `NormalizedTranscript` matching the contract schemas.

## Setup

```bash
python3.12 -m venv .venv 2>/dev/null || python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Run tests

```bash
pytest -xvs tests/transcript_ingest/
```

## Run service

```bash
.venv/bin/uvicorn transcript_ingest.api:app --host 127.0.0.1 --port 8011
```
