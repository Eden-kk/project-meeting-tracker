# Skill: meeting-memory-extraction

## Purpose

When given a fully imported meeting (transcript ready, not yet finalized):
- read the normalized transcript end-to-end
- identify decisions, action items, requirements, risks, pain points, open questions, and notable quotes
- create one draft memory card per finding
- never invent owners, dates, or claims that aren't in the transcript
- always cite the segment_ids that justify each card

## When to invoke

A meeting has reached `status="ready"` (Phase 1 ingest complete) and no
draft memory cards exist for it yet. The orchestrator runs this skill
once per ready meeting before any human review pass.

## Tools available

Only these four tools are bound for this skill:
- `get_meeting_transcript` — fetch the full normalized transcript
- `create_draft_memory_card` — record one finding at a time

(Searching existing cards and finalizing are not used here.)

## Procedure

1. Call `get_meeting_transcript(meeting_id=<the meeting>)`. If the
   transcript exceeds 100k tokens, refuse with the JSON block
   `{"refused": true, "reason": "transcript_too_large"}` and stop.
2. Read every segment. Track: which segments express agreement vs. proposal,
   who said what, any temporal markers (deadlines, dates, durations).
3. For each finding worth a card, decide its `type` from the enum:
   `decision | action_item | pain_point | quote | requirement | risk | open_question | technical_detail`.
4. Call `create_draft_memory_card` with:
   - `title` ≤ 500 chars; specific, not generic ("Auth migration delayed to Q3" not "Auth update")
   - `content` quoting or closely paraphrasing what was said
   - `source_chunk_ids` = the segment_ids that support the claim (≥1)
   - `confidence` ∈ [0, 1] reflecting how clearly the transcript states the claim
   - `speakers_json` listing the speaker_names involved
   - `source_start_ms` / `source_end_ms` from the earliest/latest cited segment when timestamps exist
5. Batch multiple `create_draft_memory_card` calls in a single assistant
   turn when possible (the runtime supports parallel tool_use blocks).
6. When every supportable finding has a card, end the turn with a
   one-paragraph summary: "Created N cards covering: <high-level list>."

## Evidence discipline

- A claim with no supporting segment_id is invented. Do not write it.
- Owners and dates only appear in cards if a speaker stated them
  explicitly. If implied but not stated, leave the field out.
- If the transcript does not support any cards (e.g. small-talk only),
  end the turn with the JSON block
  `{"refused": true, "reason": "weak_evidence"}` and create no cards.
- `confidence` ≥ 0.8 only when the transcript states the claim
  directly. Inferences max out at 0.7.

## Output contract

The runtime returns:
```
{
  "final_text": "<your closing summary>",
  "tool_calls": [{"name": ..., "input": ..., "result": ...}, ...],
  "iterations": <int>
}
```

Every successful tool_call for `create_draft_memory_card` must be a
real card backed by transcript evidence. The orchestrator audits this
list against `source_chunk_ids` to verify evidence discipline.
