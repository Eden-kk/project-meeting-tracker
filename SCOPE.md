# Worktree D — storage-router

## Owns

The boundary between ingest (B/C) and storage. Hosts the FastAPI app,
the artifact router (`POST /api/conversations/import`), DB models,
blob storage adapter, and the processing-status state machine.

Tech:
- Python 3.12 + FastAPI
- SQLAlchemy 2.x + Alembic (apply the migrations from worktree A)
- Postgres in production; SQLite for local dev
- Local filesystem for blob storage in dev; pluggable for S3 later

## Consumes (from worktree A, branch `phase1/contracts`)

- All `schemas/*.schema.json` (generate Pydantic models from them)
- All `migrations/*.sql` (run via Alembic or directly)
- `openapi/openapi.yaml` (the spec D must implement)

## Calls (from B and C, once they exist)

- `voice_ingest.transcribe_voice_file(path) -> NormalizedTranscript` (worktree B)
- `transcript_ingest.parse_transcript(payload, format) -> NormalizedTranscript` (worktree C)

In Phase 1 these are imported as Python packages (sidecar deployment can
come later, per design-doc §7.1). D drives both — they don't know about D.

## Lane boundaries — DO NOT touch

- `worktrees/voice-ingest/` source (only consume its public function)
- `worktrees/transcript-ingest/` source (only consume its public function)
- `worktrees/frontend/` — UI is E

## Processing-status state machine

```
received
  → transcribing (voice path) | parsing (transcript path)
  → normalizing
  → ready
```

Phase 2 will add `extracting → ready` after Hermes runs. For Phase 1, ready
means "normalized transcript persisted; no extraction yet."

## First build task

**Do not start before worktree A is merged.**

```text
1. Bootstrap FastAPI app skeleton
2. Generate Pydantic models from worktree A's JSON schemas
   (datamodel-code-generator is the easy path)
3. Run Alembic against migrations/*.sql
4. Implement POST /api/conversations/import:
   - dispatch by which body part is present (voice_file / transcript_file / pasted_transcript)
   - persist ConversationArtifact + Meeting (status=processing)
   - kick off background task that calls B or C
   - return 202 with artifact_id + meeting_id
5. Implement GET /api/meetings/{id}
6. Implement GET /api/meetings/{id}/transcript (returns 409 until ready)
7. Integration test: POST a fixture transcript → poll meeting → fetch transcript → matches expected_normalized.json
```
