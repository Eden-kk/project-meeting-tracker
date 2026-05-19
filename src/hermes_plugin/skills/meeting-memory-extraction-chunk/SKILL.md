# Skill: meeting-memory-extraction-chunk

## Purpose

You are processing ONE chunk (time window) of a longer meeting transcript.
The runtime has split the meeting into N fixed-duration windows and is
calling you once per window. Your job for this turn:

- read ONLY the segments for chunk `{chunk_index}` of `{chunk_count}`
  (covering meeting time `{window_start}` to `{window_end}`)
- identify decisions, action items, requirements, risks, pain points,
  open questions, and notable quotes that occur **within this window**
- create one draft memory card per finding using `create_draft_memory_card`
- end the turn with a single one-line "topic sentence" describing what
  this chunk was about (the runtime concatenates these later for the
  meeting-wide summary)

The transcript text for this chunk is embedded in the user message —
**do NOT call `get_meeting_transcript`**; you already have everything
you need.

## Tools available

Only `create_draft_memory_card` is bound. Do NOT call:
- `get_meeting_transcript` (transcript is already in the prompt)
- `search_memory_cards` (cross-chunk search is out of scope here)
- `finalize_meeting_memory` (the runtime owns finalization)

If you call any tool other than `create_draft_memory_card` the runtime
will return a tool error; treat that as a signal to stop and return
your topic sentence.

## Procedure

1. Read the transcript segments for this window. They are formatted as:
   ```
   [seg_id  start_ms-end_ms  speaker] text
   ```
2. For each finding worth a card, decide its `type` from the enum:
   `decision | action_item | pain_point | quote | requirement | risk | open_question | technical_detail`.
3. Call `create_draft_memory_card` with:
   - `meeting_id` = `{meeting_id}` (provided)
   - `title` ≤ 500 chars; specific, not generic
   - `content` quoting or closely paraphrasing what was said in this chunk
   - `source_chunk_ids` = the `seg_id`s from this window that justify the
     claim (≥1, must come from this chunk)
   - `confidence` ∈ [0, 1]; ≥0.8 only when the transcript states the
     claim directly, ≤0.7 for inferences
   - `speakers_json` listing the `speaker_name`s involved
   - `source_start_ms` / `source_end_ms` from the earliest/latest cited
     segment
4. Batch multiple `create_draft_memory_card` calls in one assistant
   turn when possible.
5. End with a single line: a one-sentence narrative beat describing
   **what was discussed in this chunk** — content, not bookkeeping.

   Good (describes the discussion):
   - "Alice and Bob agreed to move the deadline from Friday to Monday."
   - "The team debated whether to use Postgres or DynamoDB; Postgres won."
   - "Carol raised concerns about onboarding latency for new tenants."

   Bad (describes the extraction, not the discussion):
   - "Created 3 cards covering a decision and two action items."
   - "Identified two open questions about the rollout."
   - "Extracted a decision, an action item, and a risk."

   The downstream `meeting-summary-overall` skill stitches these
   one-liners into a narrative summary the user reads on the Summary
   tab. If you describe what cards you made, the summary reads as
   "this meeting was about creating cards" — which is meaningless to
   the reader. Describe **the meeting**, not your own work.

   Do NOT prefix the line with `"Chunk N/M:"` or any other index
   marker; the downstream skill consumes these as a flat ordered list.

## Evidence discipline

- A claim with no supporting `seg_id` from this window is invented.
  Do not write it.
- Do NOT reference earlier or later chunks. Each chunk stands alone.
- If this chunk has no extractable findings (small talk, silence,
  off-topic), end with the literal line `no findings` and create no
  cards.

## Output contract

The runtime collects your `create_draft_memory_card` calls (cards are
persisted by the tool itself) and your closing topic sentence. After all
chunks finish, a separate summary skill consolidates the topic sentences
into a 5-line meeting summary.
