# Skill: meeting-finalization

## Purpose

After the meeting ends:
- re-read the full transcript
- finalize selected extraction blocks
- merge duplicate draft memory cards
- verify each memory card against evidence
- downgrade unsupported claims
- create a final meeting note

## When to invoke

A meeting has been through `meeting-memory-extraction` and a human (or
the system on auto-finalize) has signaled it is ready for finalization.
The orchestrator runs this skill exactly once per meeting; calling
`finalize_meeting_memory` flips the meeting to `status="finalized"` and
freezes its memory record.

## Tools available

Only these three tools are bound for this skill:
- `get_meeting_transcript` — re-read the full transcript
- `search_memory_cards` — list current draft / candidate cards for the meeting
- `finalize_meeting_memory` — commit drafts and seal the meeting

## Procedure

1. Call `search_memory_cards(meeting_id=<id>, state="draft")` to list
   every draft card the extraction skill produced.
2. Call `get_meeting_transcript(meeting_id=<id>)` to refresh the
   evidence base.
3. For each draft card:
   - Find the cited `source_chunk_ids` in the transcript.
   - If the cited segments do NOT support the claim, the card should be
     downgraded (flag it in the closing summary; do not call create —
     that requires a separate edit pass out of scope here).
   - If two draft cards describe the same finding, note the duplication
     for the human reviewer (this skill does not delete cards itself).
4. Once the audit is complete and you are satisfied that the surviving
   drafts are evidence-backed, call `finalize_meeting_memory(meeting_id=<id>)`.
   The server commits the drafts and freezes the meeting.
5. End the turn with a structured summary that lists:
   - cards reviewed (count by type)
   - cards flagged for downgrade (with `memory_card_id` + reason)
   - duplicate clusters (with the `memory_card_id`s involved)
   - the `committed_card_ids` returned by `finalize_meeting_memory`

## Evidence discipline

- Never invent a card during finalization. This skill audits and seals.
- Never call `finalize_meeting_memory` before reading the transcript —
  the order matters because the audit depends on fresh evidence.
- If the meeting transcript is empty or all cards lack evidence, refuse
  with `{"refused": true, "reason": "weak_evidence"}` and do not
  finalize.

## Output contract

```
{
  "final_text": "<structured audit summary>",
  "tool_calls": [...],
  "iterations": <int>
}
```

The closing summary must include the `committed_card_ids` list verbatim
from the finalize tool's result so downstream consumers can pick it up.
