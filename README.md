# project-meeting-tracker

A Hermes-powered meeting memory product. Three backend services + one frontend, all in this monorepo.

## Layout

| Path | What it is |
|---|---|
| `src/storage_router/` | FastAPI artifact router + Postgres persistence + ingest dispatcher. Hosts `/api/conversations/import`, `/api/meetings`, `/api/meetings/{id}`, `/api/meetings/{id}/transcript`, plus `/docs` (Swagger) and the built frontend SPA when `FRONTEND_DIST` is set. |
| `src/transcript_ingest/` | Standalone FastAPI service (`POST /transcript/parse`). Detects format (txt/md/vtt/srt/json) and parses speakers + timestamps. |
| `src/voice_ingest/` | Standalone FastAPI service (`POST /voice/transcribe`). Runs faster-whisper STT + pyannote diarization. |
| `src/` (frontend roots: `src/api/`, `src/pages/`, `src/components/`, `src/layouts/`, `src/hooks/`, `src/lib/`, `src/mocks/`) | Vite + React + TypeScript SPA. |
| `schemas/`, `migrations/`, `openapi/`, `fixtures/` | Tier-0 contracts shared by all services. |
| `alembic/` | Storage-router migrations (Postgres). |
| `tests/storage_router/`, `tests/transcript_ingest/`, `tests/voice_ingest/` | Per-service test suites. |
| `e2e/` | Playwright end-to-end tests for the SPA. |

## Per-service docs

- `README-storage-router.md` — storage-router setup + DSN config
- `README-transcript-ingest.md` — transcript-ingest setup
- `README-voice-ingest.md` — voice-ingest setup (Whisper + diarization)

## Per-service scopes (lane boundaries from the original parallel-development plan)

- `SCOPE-storage-router.md` (Worktree D)
- `SCOPE-transcript-ingest.md` (Worktree C)
- `SCOPE-voice-ingest.md` (Worktree B)
- `SCOPE-frontend.md` (Worktree E)

## Deployment topology

```
                      browser
                         │
                         ▼
                   single tunnel
                         │
                         ▼
              storage-router (uvicorn :8000)
       ┌──────────────────────────────────────────┐
       │  /              → built frontend SPA     │
       │  /docs          → FastAPI Swagger        │
       │  /api/*         → JSON endpoints         │
       └──────────────┬───────────────────────────┘
                      │
       ┌──────────────┼─────────────────────────┐
       │              │                         │
       ▼              ▼                         ▼
  Postgres 16    voice-ingest               transcript-ingest
                127.0.0.1:8021             127.0.0.1:8011
                Whisper + diarize          format detect + parse
```

Each service runs in its own venv; storage-router calls the ingest services over loopback HTTP. See PR #7 for the integration that wired this together.

## Build + test (per service)

Each service has its own dependency manifest. Pick the relevant one:

```bash
# storage-router (uses pyproject.toml)
python3.12 -m venv .venv-storage && .venv-storage/bin/pip install -e '.[dev]'

# transcript-ingest (light: webvtt-py + srt + fastapi)
python3.12 -m venv .venv-transcript && .venv-transcript/bin/pip install -r requirements-transcript.txt

# voice-ingest (heavy: faster-whisper + pyannote + torch + edge-tts)
python3.12 -m venv .venv-voice && .venv-voice/bin/pip install -r requirements-voice.txt

# frontend
pnpm install && pnpm dev
```

(In practice this repo currently uses one `.venv` per service worktree under `worktrees/`; the per-service requirements files at root let any worktree install only what it needs.)

## Status

Phase 1 complete: design doc at `docs/design-doc.md`, roadmap at `docs/roadmap.md`. The five Phase-1 worktrees and the integration are all merged.
