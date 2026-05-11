# Skill: live-meeting-extraction

## Purpose

You are processing a SHORT, RECENT window of a meeting that is **still
in progress**. The runtime fires you every ~2 minutes with the
transcript segments produced since the last tick (with a 30s overlap
on either side so a decision spoken across the boundary is not lost).
Your job for this turn:

- read the segments embedded in the user message (they cover meeting
  time `{window_start}` to `{window_end}`),
- identify decisions, action items, requirements, risks, pain points,
  open questions, and notable quotes that occur **within this window**,
- create one draft memory card per finding using
  `create_draft_memory_card`,
- end the turn with a single one-line summary of what this window was
  about (the runtime logs it for the operator; it is NOT shown in the
  UI).

The transcript text for this window is embedded in the user message —
**do NOT call `get_meeting_transcript`**; you already have everything
you need. The runtime did the windowing for you.

## Tools available

Only `create_draft_memory_card` is bound. Any other tool call returns
a 403 error to you and you should stop and emit your one-line summary.

## Procedure

1. Read the transcript segments for this window. They are formatted as:
   ```
   [seg_id  start_ms-end_ms  speaker] text
   ```
2. For each finding worth a card, decide its `type` from the enum:
   `decision | action_item | pain_point | quote | requirement | risk | open_question | technical_detail`.
3. Call `create_draft_memory_card` with:
   - `meeting_id` = `{meeting_id}` (provided in the bootstrap)
   - `title` ≤ 500 chars; specific, not generic
   - `content` quoting or closely paraphrasing what was said in this
     window
   - `source_chunk_ids` = the `seg_id`s from this window that justify
     the claim (≥1, must come from this window)
   - `confidence` ∈ [0, 1]; ≥0.8 only when the transcript states the
     claim directly, ≤0.7 for inferences
   - `speakers_json` listing the `speaker_name`s involved
   - `source_start_ms` / `source_end_ms` from the earliest/latest cited
     segment
4. Batch multiple `create_draft_memory_card` calls in one assistant
   turn when possible.
5. End with a single line:
   `"Live window {window_start}-{window_end}: <one-sentence topic>"`

## Live-specific guidance

- The 30s overlap with the prior window means you may see one or two
  segments you've already extracted on a prior tick. The downstream
  consolidation pass at meeting `/end` merges duplicates — extract
  freely if a finding lands inside this window even if it was at the
  tail end of the prior one. Better to over-emit and let
  consolidation merge than to silently drop a boundary-spanning
  decision.
- Many windows will contain small talk, transitions, or partial
  utterances. If there is nothing worth a card, end with
  `"Live window {window_start}-{window_end}: no findings"` and
  create no cards.
- Confidence in live mode: clamp inferences to ≤0.6 because the audio
  is partial — what sounds like a decision may be reversed in the
  next minute. Keep ≥0.8 only for unambiguous, completed statements.

## Evidence discipline

- A claim with no supporting `seg_id` from this window is invented.
  Do not write it.
- Do NOT reference earlier or later windows. Each window stands alone.
- Do NOT speculate about what will be decided next.

## Output contract

The runtime collects your `create_draft_memory_card` calls (cards are
persisted by the tool itself) and your closing one-line summary. The
caller writes the high-water mark (`last_live_extraction_end_ms`) back
to the meeting row so the next tick processes the next window.
