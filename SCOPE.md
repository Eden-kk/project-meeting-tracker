# Worktree H — memory-cards-frontend (Phase 2)

## Owns

The two Meeting Review tabs that are currently disabled placeholders (per design-doc §5.3): **Memory Cards** and **Ask Hermes**. Plus the small dashboard surface that surfaces "needs-review" memory cards to the user globally.

Tech:
- Vite + React 18 + TypeScript 5 (matches existing frontend stack)
- TanStack Query 5 + axios
- Tailwind CSS
- MSW 2 (dev mocks for the 7 new endpoints until backend lands)

## New surfaces

### Memory Cards tab (on `MeetingReviewPage`)

Replaces the disabled placeholder. Shows the meeting's draft + committed cards in a card-grid layout:
- One card per memory card; type icon (decision/action_item/etc.); title; content snippet; speaker chips; evidence link.
- Action bar per draft card: Approve / Edit / Reject buttons (calls POST /api/memory-cards/{id}/commit | reject | PATCH).
- Filter chips at top: type, state.
- Empty state if zero cards.

### Ask Hermes tab (on `MeetingReviewPage`)

Replaces the disabled placeholder. Chat-style:
- User types a question about this meeting.
- POST /api/qa/meeting → renders answer + evidence citations (clickable to scroll to the transcript segment).
- History of recent Q&As in this session (client-side state only; not persisted in Phase 2).

### Dashboard "needs review" surface (HomePage)

New StatChip on HomePage: "Cards needing review: N" — count of draft cards across all meetings the workspace owns. Clicking it filters the meetings list by has-pending-cards.

## Consumes (from main)

- `openapi/openapi.yaml` — the 7 new endpoints, regenerated into `src/api/types.ts` after the **memory-cards-backend** worktree merges. Until then, MSW mocks the surface.
- `schemas/memory_card.schema.json` — already on main; informs Pydantic-equivalent TS types.
- Existing frontend components: `Tabs`, `TranscriptView`, `Sidebar`, `StatChip`, `EmptyState`, `MeetingCard`, `MeetingTable`. Reuse, don't fork.
- Existing API client: extend `src/api/client.ts` with new wrappers (`createMemoryCard`, `listMeetingCards`, `commitCard`, etc.) — do NOT replace existing wrappers.

## Lane boundaries — DO NOT touch

- `src/storage_router/`, `src/hermes_plugin/`, `src/transcript_ingest/`, `src/voice_ingest/` — this is a UI-only worktree.
- `openapi/openapi.yaml` — DO NOT modify. Schema additions land via worktree G; this worktree consumes them via `pnpm gen:api`.
- `e2e/import-to-review.spec.ts` + the existing sidebar Playwright spec — extend with new test files, don't modify existing assertions.

## Cross-worktree dep handling

- **Pre-backend-merge**: implement against the OpenAPI shape this worktree EXPECTS (mirroring backend's planned schema). MSW returns canned cards / canned QA answers. All UI flows testable.
- **Post-backend-merge**: rebase onto main, run `pnpm gen:api` to refresh types, swap MSW handlers for live (or keep both; MSW only fires in dev).

## First build task

**Can start in parallel with worktrees F and G.** MSW-first development works fine.

```text
1. Author the expected backend OpenAPI shape inline as TypeScript types in src/api/memory_cards.types.ts (will be replaced by gen:api once worktree G merges)
2. Add MSW handlers for the 7 endpoints with canned data
3. Build MemoryCardsTab component + MemoryCardItem subcomponent
4. Build AskHermesTab component with the chat-style UI
5. Wire both into MeetingReviewPage; remove the disabled placeholder + tooltip
6. Add the "Cards needing review" StatChip to HomePage
7. vitest: MemoryCardsTab + AskHermesTab unit tests against MSW
8. Playwright: e2e/memory-cards.spec.ts — paste a transcript → wait for ready → switch to Memory Cards tab → see cards → approve one → assert state change
```

## Tests

Vitest tests live alongside components per existing convention (`src/components/__tests__/` and `src/pages/__tests__/`). Playwright at `e2e/`. No backend tests needed.
