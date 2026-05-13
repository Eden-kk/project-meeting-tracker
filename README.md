# project-meeting-tracker

A Hermes-powered meeting memory tracker. Ingests transcripts (VTT/TXT) or
audio (WAV/MP3 → Modal-hosted Whisper + pyannote diarization) on a
per-workspace basis, extracts eight kinds of typed memory cards
(decisions, action items, pain points, requirements, risks, open
questions, quotes, technical details), and lets users browse a per-meeting
narrative summary or ask Hermes natural-language questions across the
whole workspace with `[card]` / `[src]` clickable citations.

## Architecture overview

Three FastAPI services + one Vite/React SPA, all in this monorepo. The
LLM backend is provider-switchable at runtime (`LLM_PROVIDER=anthropic`
or `LLM_PROVIDER=openai`); the same `SKILL.md` prompts run under either
dispatcher. Data is isolated per workspace (`workspace_id` filter at the
SQL layer for every read path).

```
                browser
                   |
                   v
          SPA (React Router)
            /ws/:workspaceId/*
                   |
                   v
          storage-router (port 8050)
          ├── Postgres-15 (meetings, transcripts, memory_cards, workspaces)
          ├── Hermes runtime  (src/hermes_plugin/, anthropic | openai)
          ├── transcript-ingest (HTTP, port 8011)   ← VTT/SRT/TXT/MD/JSON parser
          └── voice-ingest      (HTTP, Modal)        ← faster-whisper + pyannote
```

| Path | What it is |
|---|---|
| `src/storage_router/` | FastAPI gateway. Hosts `/api/conversations/import`, `/api/meetings*`, `/api/memory-cards*`, `/api/workspaces*`, `/api/search/*`, `/docs` (Swagger), and serves the SPA when `FRONTEND_DIST` is set. |
| `src/transcript_ingest/` | Standalone FastAPI service. Detects format (txt/md/vtt/srt/json) and parses speakers + timestamps. |
| `src/voice_ingest/` | Standalone FastAPI service. Runs faster-whisper STT + pyannote diarization. mp4 video containers are accepted; audio is stripped via ffmpeg before transcribe. |
| `src/hermes_plugin/` | Hermes plugin loader + skill runtime. Skills live in `src/hermes_plugin/skills/<name>/SKILL.md` (prompt template + tool bindings + max-iterations metadata). |
| `src/` (frontend roots: `src/api/`, `src/pages/`, `src/components/`, `src/layouts/`, `src/hooks/`, `src/lib/`, `src/mocks/`) | Vite + React + TypeScript SPA. Routes in `src/App.tsx`. |
| `schemas/`, `migrations/`, `openapi/`, `fixtures/` | Tier-0 contracts shared by all services. |
| `alembic/` | Storage-router migrations (Postgres). |
| `tests/storage_router/`, `tests/transcript_ingest/`, `tests/voice_ingest/`, `tests/hermes_plugin/` | Per-service test suites. |
| `e2e/` | Playwright end-to-end tests for the SPA. |

## User-facing routes (SPA)

All routes are workspace-scoped under `/ws/:workspaceId/`.

| Route | Purpose |
|---|---|
| `/meetings` | Home — list of meetings in this workspace; click into one to review. |
| `/import` | Upload a transcript (VTT/TXT/SRT) or audio file (WAV/MP3/mp4-video → audio extracted server-side). Auto-finalize after parse. |
| `/live` | Real-time mic capture + on-the-fly extraction: live current-topic banner, live-summary, **interview-questioner** proposing follow-up questions every 60 s. |
| `/ask` | Workspace-level Ask Hermes — natural-language QA across every meeting in the workspace, with `[card]` / `[src]` citations that deep-link back into the source meeting. |
| `/meetings/:id/processing` | Status page while a meeting is mid-extraction; auto-advances when finalized. |
| `/meetings/:id` | Review tabs: **Summary** (narrative TL;DR + What we covered + Notes), **Transcript** (with click-to-Ask), **Memory Cards** (8 typed kinds), **Ask Hermes** (in-meeting QA), Share/Export (disabled — Phase 8). |
| `/action-items` | Aggregated action_item cards across all workspace meetings. |
| `/open-questions` | Aggregated open_question cards across all workspace meetings. |
| `/settings` | Workspace settings (placeholder). |

## Production / test deployment

### App pod (RunPod CPU)

- Pod ID: `riz0b05s7yg7ab` ("tracker-app-2026-05-12")
- Public URL: `https://riz0b05s7yg7ab-8050.proxy.runpod.net/`
- Runs storage-router (port 8050), transcript-ingest (port 8011), Postgres-15 locally (`tracker` DB).
- SSH: `ssh -p 41734 -i ~/.ssh/id_ed25519 root@213.192.2.103`
- Code: `/workspace/app` (git checkout of this repo, on `main`)
- Logs: `/var/log/tracker-app.log` (storage-router), `/var/log/transcript-ingest.log`
- Restart pattern: `kill <uvicorn-pid>` and re-run the launcher in `start-router.sh` (or the inline env+nohup snippet captured in the launch logs).

### Voice-ingest (Modal)

- Deployed in the `hao-ai-lab` Modal workspace as `voice-ingest`.
- Public URL: `https://hao-ai-lab--voice-ingest-fastapi.modal.run`
- A10G GPU, faster-whisper `large-v3`, pyannote.audio 3.3.2.
- HuggingFace token bound via the Modal Secret named `hf-token-tracker`.
  **Do NOT** overwrite the older Modal Secret named `hf-token` — it
  belongs to a different teammate.

### Local dev

- Backend: `python3.12 -m venv .venv && source .venv/bin/activate && pip install -e .`
- Migrations: `DATABASE_URL=... alembic upgrade head`
- SPA: `npm install && npm run dev` (Vite, port 5173)
- Provider key: set `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` (the runtime picks one based on `LLM_PROVIDER`)

## Existing features

**Import & ingest**
- VTT, TXT, SRT, MD, JSON transcripts.
- Audio: WAV, MP3, M4A, OGG, WebM, **and mp4 video containers** (audio
  track is extracted with ffmpeg before transcribe).
- Auto-finalize after parse: chunked extraction → audit pass → consolidation pass → narrative summary.

**Live recording**
- On-the-fly extraction with current-topic banner and live summary.
- Interview-questioner skill suggests 3–5 follow-up questions every 60 s
  in interview mode.

**Memory cards (8 typed kinds)**
- decision, action_item, pain_point, requirement, risk, open_question,
  quote, technical_detail.
- Audit pass auto-hides low-confidence cards (`hidden_at`).
- Consolidation pass merges duplicates via supersede-into.

**Summary tab**
- New narrative format: TL;DR (≤30 words) + What we covered + optional
  Notes. No duplication of cards-tab content.
- Rendered as markdown via the shared `AnswerBody` component.

**Ask Hermes**
- Per-meeting QA inside the meeting review tab.
- Workspace-wide QA at `/ws/:workspaceId/ask` with citations that
  deep-link back to the source meeting + segment.
- Citation tokens: `[card]`, `[card:<id>]`, `[seg:<id>]`,
  `[project:<ws>:meeting:<m>:card:<c>]`.

**Workspace switcher**
- URL-keyed routing under `/ws/:workspaceId/...`.
- Sidebar workspace picker.
- localStorage meetings cache scoped per workspace (no cross-workspace leakage).

**Cross-meeting aggregation**
- `/action-items` and `/open-questions` roll up cards across the workspace.

**Speaker rename**
- `PATCH /api/meetings/:id/speakers` with `{from, to}` rewrites
  `speaker_label_map` and re-applies to all transcript segments + cards.

## Reversibility / "undo" primitives

There is **no explicit Undo button** in the UI yet. The reversible
primitives in the system today:

- **Card hide** (`POST /api/memory-cards/:id/hide`) — soft-deletes via
  `hidden_at`. Hidden cards survive in the row store; pass
  `?include_hidden=true` on the list endpoint to fetch them.
- **Card supersede** (`POST /api/memory-cards/:loser/supersede-into/:winner`)
  — consolidation merges duplicates: loser is hidden, winner stays.
- **Speaker rename** — reversible by patching back with `{from: to, to: from}`.
- **Self-healing meetings registry** — `useMeetings` prunes localStorage
  entries the server no longer recognizes (stale bookmark, deleted meeting).

## Roadmap / planned features

- **Slack bot MVP** — auto-post on finalize + @mention QA. PR #71 open.
- **Manual hide / unhide of memory cards** from the SPA (backend exists; UI doesn't).
- **Trash + restore for meetings** (`DELETE /api/meetings/:id` route does not exist yet).
- **Per-project subagents + orchestrator routing** — data layer shipped in #72; the orchestrator-skill routing layer that dispatches `workspace-qa` to a per-project subagent is deferred.
- **Multi-Slack-workspace support** (current MVP is single-workspace by env).
- **Share / Export tab** (currently disabled in `MeetingReviewPage`).
- **Audit / undo speaker rename via UI** (would need a `speaker_label_map` history stack).

## Per-service docs

- `README-storage-router.md` — storage-router setup + DSN config
- `README-transcript-ingest.md` — transcript-ingest setup + supported formats
- `README-voice-ingest.md` — voice-ingest setup (Whisper, diarization, HF token, model defaults)
