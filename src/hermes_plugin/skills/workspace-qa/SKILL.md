# Skill: workspace-qa

## Purpose

Answer a free-form question about anything the user has ever recorded
in this workspace — across every meeting. Cite evidence by deep-link so
the SPA can jump to the originating meeting + card or segment.

## When to invoke

The user navigates to `/ask` and types a question. The orchestrator
passes `workspace_id` and the question text. This skill mutates no state.

## Tools available

Only these two cross-meeting tools are bound for this skill:

- `search_workspace_cards(q, type?)` — primary lookup. Memory cards are
  pre-distilled evidence, so a card hit is the strongest possible answer.
- `search_workspace_transcripts(q)` — fallback when no card mentions the
  topic. Hits are raw speaker segments.

## Procedure

1. Read the question carefully. Identify the `type` of memory most
   relevant (decision, action_item, requirement, etc.) if obvious.
2. Call `search_workspace_cards(workspace_id=..., q=<keywords>)`.
   - Optionally pass `type=<type>` to narrow.
   - Read the title + content + meeting_title of every returned hit.
3. If one or more cards answer the question:
   - Compose the answer from those cards.
   - Cite each card inline as `[meeting:<meeting_id>:card:<memory_card_id>]`.
   - Stop — do not call the transcript tool.
4. If no card answers OR the cards are vague:
   - Call `search_workspace_transcripts(workspace_id=..., q=<keywords>)`.
   - Read the speaker + meeting_title + text of every hit.
   - If found, answer and cite each transcript hit inline as
     `[meeting:<meeting_id>:seg:<segment_id>]`.
   - If not found, refuse with the JSON block
     `{"refused": true, "reason": "weak_evidence"}` and list the search
     terms you tried.
5. Never invent dates, owners, or decisions. Better to refuse than to
   guess.

## Evidence discipline

- Every claim must be traceable to one of the two citation forms above.
  Inline citations are mandatory.
- If multiple meetings disagree on the same decision, surface the
  conflict and cite both meetings. Do not pick a "winner".
- When a card has low confidence (< 0.5), hedge in the prose:
  "It appears that … but the supporting card is low-confidence."

## Output contract

```
{
  "final_text": "<answer with inline citations using [meeting:M:card:C] or [meeting:M:seg:S] patterns>",
  "tool_calls": [...],
  "iterations": <int>
}
```

The storage-router route `/api/qa/workspace` parses the citations out of
`final_text` so the SPA can deep-link.
