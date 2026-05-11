# Skill: meeting-qa

## Purpose

When answering meeting questions:
- search memory cards first
- then transcript segments
- cite evidence
- say when evidence is weak
- avoid inventing owners, dates, or decisions

## When to invoke

A user asks a question about a specific meeting. The orchestrator
passes the meeting_id and the question text. This skill does not
mutate any state.

## Tools available

Only these two tools are bound for this skill:
- `search_memory_cards` — primary lookup; cards are evidence-backed by
  construction
- `get_meeting_transcript` — fallback when no cards address the question

## Procedure

1. Read the question carefully. Identify the `type` of memory most
   relevant (decision, action_item, requirement, etc.) if obvious.
2. Call `search_memory_cards(meeting_id=<id>)`. Optionally filter by
   `type` if the question targets a specific kind. Inspect every card's
   `title` and `content`.
3. If one or more cards answer the question:
   - Compose the answer from those cards.
   - Cite each card's `memory_card_id` and `source_chunk_ids` inline.
   - End the turn.
4. If no card answers the question OR the cards are too vague:
   - Call `get_meeting_transcript(meeting_id=<id>)`.
   - Search the segments for the answer.
   - If found, answer and cite `segment_id`s.
   - If not found, refuse with the JSON block
     `{"refused": true, "reason": "weak_evidence"}` and explain which
     sources you searched.
5. Never invent an owner, date, or decision. Better to say "the
   transcript does not state the owner" than to guess.

## Evidence discipline

- Every claim in the final answer must be traceable to either a
  `memory_card_id` or a `segment_id`. Inline citations are mandatory.
- If multiple cards conflict, surface the conflict instead of picking
  one. Cite both.
- Tone: factual and brief. The user wants the answer plus the
  evidence, not a re-explanation of the meeting.

## Output contract

```
{
  "final_text": "<answer with inline citations>",
  "tool_calls": [...],
  "iterations": <int>
}
```

`final_text` must include at least one citation token of the form
`[card:<memory_card_id>]` or `[seg:<segment_id>]` whenever an answer
is provided. The refusal JSON is the only acceptable answer-free
output.
