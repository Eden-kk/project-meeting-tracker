# Worktree G — memory-cards-backend (Phase 2)

## Owns

The storage-router endpoints that surface meeting memory cards + Hermes Q&A. Plus the Pydantic / ORM models and the Alembic migration.

Tech:
- Python 3.12 + FastAPI 0.115 (matches existing storage-router stack)
- SQLAlchemy 2.x + Alembic
- Postgres 16 (per Phase 1 contracts decision; SQLite still NOT supported)

## New endpoints (per design-doc §17)

```
POST   /api/memory-cards                    create draft (called by Hermes plugin)
GET    /api/meetings/{id}/memory-cards      list cards for a meeting; filter by type/state
PATCH  /api/memory-cards/{id}               edit by user
POST   /api/memory-cards/{id}/commit        promote draft → committed
POST   /api/memory-cards/{id}/reject        promote draft → rejected
POST   /api/meetings/{id}/finalize          run extraction (sync; for Phase 2 this just triggers Hermes plugin's meeting-finalization skill)
POST   /api/qa/meeting                      Q&A against a single meeting; body: { meeting_id, question }
```

The 7 routes ship as ONE worktree because their shared concerns (memory_cards table, MemoryCard Pydantic, MemoryCard ORM) are best edited together.

## Migration

`migrations/0008_memory_cards_active.sql` (or similar — check the next free number). The `memory_cards` table already exists from the contracts migration `0004_memory.sql`, but Phase 1 never used it. This worktree may add an index (`idx_cards_state_meeting`), tighten a constraint, or add a `created_by_user_id` column if needed for the PATCH/commit/reject ownership checks.

## Consumes (from main)

- `schemas/memory_card.schema.json` — already on main; types match.
- `migrations/0004_memory.sql` — defines the `memory_cards` table; this worktree extends, doesn't replace.
- `src/storage_router/api/app.py`, `src/storage_router/storage.py` — extends, doesn't fork.
- `openapi/openapi.yaml` — adds the 7 new operation entries.

## Lane boundaries — DO NOT touch

- `src/hermes_plugin/` — that's worktree F. The plugin calls these endpoints; this worktree doesn't know about the plugin.
- Frontend (`src/components/`, `src/pages/`, etc.) — worktree H.
- `tests/transcript_ingest/`, `tests/voice_ingest/`, `tests/hermes_plugin/` — own subdir at `tests/storage_router/test_memory_cards*.py`.
- Phase-1 endpoints: `/api/conversations/import`, `/api/meetings`, `/api/meetings/{id}`, `/api/meetings/{id}/transcript` — read-only consumers; don't modify their behavior.

## OpenAPI ownership

This worktree owns the OpenAPI additions for all 7 routes. The frontend worktree (H) regenerates `src/api/types.ts` after this worktree merges; until then, frontend mocks the surface in MSW.

## QA endpoint design

`POST /api/qa/meeting` is a thin orchestration:
1. Receive `{ meeting_id, question }`.
2. Invoke the Hermes plugin's `meeting-qa` skill (in-process if Hermes is in the same venv, or HTTP if Hermes runs as a sidecar — Phase 2 default is in-process for simplicity).
3. Return `{ answer: str, evidence: [{ chunk_id, segment_ids, snippet }] }` per design-doc §15 meeting-qa contract.

Phase 2 ships a stub Hermes runtime: when called, the QA endpoint shells out to a Python subprocess that loads the hermes_plugin module and calls its skill function. Real Hermes runtime supervision is Phase 4.

## First build task

**Do not start before main has the Phase 1 integration merged** (PR #7 is in; ✓).

```text
1. Add 7 OpenAPI operations + Meeting/MemoryCard JSON in openapi/openapi.yaml
2. Author Pydantic MemoryCardCreate, MemoryCardUpdate, MemoryCardOut
3. Add SQLAlchemy ORM model for MemoryCard (mirrors migrations/0004_memory.sql columns)
4. New file src/storage_router/api/memory_cards_route.py for the 5 cards routes
5. New file src/storage_router/api/qa_route.py for /api/qa/meeting + finalize
6. Update src/storage_router/api/app.py to include the new routers
7. Storage helpers in src/storage_router/storage.py: create_card, list_cards, patch_card, transition_card_state, etc.
8. Migration 0008 if any column tweaks needed (else skip)
9. Tests under tests/storage_router/test_memory_cards.py + test_qa.py — use the existing live-Postgres conftest
```

## Tests

Use the existing `tests/storage_router/conftest.py` (live Postgres + autouse cleanup).
