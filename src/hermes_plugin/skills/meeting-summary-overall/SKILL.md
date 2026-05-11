# Skill: meeting-summary-overall

## Purpose

The runtime has just finished processing every chunk of a long meeting
through `meeting-memory-extraction-chunk`. Each chunk produced a single
"topic sentence" describing what it was about. Your job is to read those
sentences and emit one cohesive 5-line summary of the whole meeting.

## When to invoke

After per-chunk extraction completes. The runtime calls this skill
exactly once per finalize.

## Tools available

**No tools are bound.** Do not attempt any tool calls; the runtime
ignores any `tool_use` blocks for this skill.

## Procedure

1. Read the per-chunk topic sentences (provided in the user message,
   one per line).
2. Synthesize them into a 5-line summary covering:
   - the overall theme / purpose of the meeting
   - the most consequential decisions
   - the action items and their owners (if stated)
   - any unresolved questions or risks
   - one closing line of context (e.g. "Workshop ran 90 min; speakers: Alice, Bob, Carol.")
3. Keep each line short (≤140 chars). Do not invent specifics not
   present in the per-chunk sentences.
4. Return ONLY the 5-line summary as your turn's text — no preamble,
   no explanation, no markdown bullets.

## Evidence discipline

- The topic sentences are your only ground truth. If they say nothing
  about action items, do not invent one.
- If there are zero useful topic sentences (empty / "no findings" only),
  return the single line `"Meeting had no extractable content."`.
