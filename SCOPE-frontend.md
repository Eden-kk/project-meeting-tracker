# Worktree E — frontend

## Owns

The web UI for Phase 1: Import Existing Conversation, processing-status
view, and the basic Meeting Review Page.

Tech:
- React 18 + Vite + TypeScript
- TanStack Query for API calls
- API client generated from `openapi/openapi.yaml` (worktree A)
- Tailwind for styling (cheap, ergonomic)

## Consumes (from worktree A, branch `phase1/contracts`)

- `openapi/openapi.yaml` — generate the typed API client from this. While
  worktree D is being built, mock the responses (MSW or hand-rolled).

## Phase-1 surface (per roadmap.md)

```
Page: Import Existing Conversation (design-doc §5.2 / §18.3)
  - drag-and-drop zone
  - paste-transcript textarea
  - metadata: title, visibility, labels
  - submit → POST /api/conversations/import → redirect to processing view

Page: Processing View (design-doc §18.4)
  - poll GET /api/meetings/{id}
  - show stage list per status: received → transcribing/parsing → normalizing → ready
  - on ready, link to Meeting Review Page

Page: Meeting Review (design-doc §5.3) — Phase-1 scope ONLY
  - Tabs:
    - Summary (placeholder — populated in Phase 2 when Hermes lands)
    - Transcript (full; renders normalized transcript with speaker + timestamp)
  - Deferred tabs (DO NOT build):
    - Memory Cards    → Phase 2
    - Ask Hermes      → Phase 7
    - Share / Export  → Phase 8
```

## Lane boundaries — DO NOT touch

- All backend worktrees. E talks to D only over HTTP per the OpenAPI spec.
- Do not invent endpoints not in `openapi/openapi.yaml`. If you need
  something new, propose adding it to the spec (worktree A round 2).

## First build task

**Can start in parallel with D once worktree A is merged**, since E mocks
the API surface from openapi.yaml.

```text
1. pnpm create vite@latest . -- --template react-ts
2. Install: tanstack-query, axios, openapi-typescript, msw, tailwindcss
3. Generate types: openapi-typescript ../contracts/openapi/openapi.yaml -o src/api/types.ts
4. Set up MSW handlers that return fixture responses
5. Build the three pages above against MSW
6. Once D is reachable, swap MSW out for the real backend
7. E2E happy path: upload sample_transcript.vtt → see processing → see transcript
