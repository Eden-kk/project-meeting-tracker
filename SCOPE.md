# Worktree F — hermes-plugin (Phase 2)

## Owns

The Hermes Agent plugin module that lives alongside Hermes (or in a sidecar process) and exposes meeting-memory tools to the agent. Plus the three Phase-2 Hermes skill markdown files.

Tech:
- Python 3.12 + Pydantic v2 (matches existing storage-router stack)
- httpx (sync client) for calling storage-router's `/api/*` from inside tool implementations
- pyyaml for `plugin.yaml`
- Anthropic Python SDK (`anthropic`) for the live runtime — the smoke test exercises the plugin against real Claude when `ANTHROPIC_API_KEY` is set; mocks are used for unit tests when it is not

Layout:
```
src/hermes_plugin/
├── plugin.yaml              # plugin manifest (per design-doc §14)
├── __init__.py              # registers tools
├── schemas.py               # JSON-schema definitions for each tool
├── tools.py                 # tool implementations (call client.py)
├── client.py                # httpx wrapper around STORAGE_ROUTER_URL
└── skills/
    ├── meeting-memory-extraction/SKILL.md
    ├── meeting-finalization/SKILL.md
    └── meeting-qa/SKILL.md
```

## Consumes (from main)

- `openapi/openapi.yaml` — defines the `/api/*` surface the plugin's `client.py` calls. The new memory-cards endpoints are added by the **memory-cards-backend** worktree; this worktree mocks them via `httpx.MockTransport` until that branch merges, then switches to live.
- `schemas/memory_card.schema.json` (already in main from Phase 1 contracts) — drives the Pydantic types used by `create_draft_memory_card` tool input validation.
- `docs/design-doc.md` §13 (memory card model), §14 (plugin design), §15 (skills purpose). Read-only.

## Tools shipped (Phase-2 subset per roadmap)

```
get_meeting_transcript      → GET /api/meetings/{id}/transcript
search_memory_cards         → GET /api/meetings/{id}/memory-cards (filter by type/state)
create_draft_memory_card    → POST /api/memory-cards
finalize_meeting_memory     → POST /api/meetings/{id}/finalize
```

Deferred to Phase 4: live tools (`get_live_meeting_state`, `update_meeting_pattern`, `update_dynamic_schema`, `get_recent_transcript_chunks`).

## Skills shipped

- `meeting-memory-extraction` — given a meeting's full transcript, extract draft memory cards. Reads chunks → infers blocks → calls `create_draft_memory_card` per finding.
- `meeting-finalization` — re-read transcript, merge duplicate drafts, downgrade unsupported claims, produce the meeting note.
- `meeting-qa` — answer a question about a meeting; search cards → summaries → chunks; cite evidence; refuse when evidence is weak.

## Lane boundaries — DO NOT touch

- `src/storage_router/` — that's worktree G (memory-cards-backend). This worktree only consumes its endpoints over HTTP.
- `src/transcript_ingest/`, `src/voice_ingest/` — already merged Phase-1 services; don't modify.
- Frontend roots (`src/api/`, `src/pages/`, etc.) — that's worktree H.
- `tests/storage_router/`, `tests/transcript_ingest/`, `tests/voice_ingest/` — own subdir tests at `tests/hermes_plugin/`.
- `openapi/openapi.yaml` — DO NOT modify. The endpoints this plugin calls are added by worktree G; this worktree READS them (post-merge) but does not author them.

## Anthropic API key

Live tests need `ANTHROPIC_API_KEY` in the env. Without it:
- Unit tests (mocked Anthropic responses): pass.
- Skill smoke runs (scripts/smoke_extraction.py): skip with a clear "ANTHROPIC_API_KEY required" message.

The dev box does NOT currently have one set; the user will export it before live runs.

## First build task

**Do not start before contracts (memory_card.schema.json) and storage-router endpoints are confirmed in main.** memory_card.schema.json is already there; the new endpoints arrive when worktree G merges. Until then, mock the HTTP calls.

```text
1. python3.12 -m venv .venv && .venv/bin/pip install -e '.[dev]' (uses storage-router's pyproject.toml)
   plus: pip install pyyaml anthropic
2. Author plugin.yaml + schemas.py + client.py + tools.py + __init__.py
3. Three skills/SKILL.md files (one per skill, per the design-doc §15 templates)
4. Tests/hermes_plugin/test_tools.py — httpx.MockTransport asserting the right /api/* URL is called with the right body
5. Tests/hermes_plugin/test_skills_smoke.py — invokes meeting-memory-extraction against a fixture transcript using a mocked Anthropic client; assert N draft cards created
6. scripts/smoke_extraction.py — live smoke (skips if no ANTHROPIC_API_KEY)
```

## Tests subdir

`tests/hermes_plugin/` (with its own conftest.py for mock fixtures). Matches the per-service split from Phase 1.
