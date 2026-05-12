# Skill: live-topic-tracker

## Purpose

The storage-router invokes this skill every 30 s while a meeting is `live`.
You receive a plain-text snippet (the last ≤60 s of finalized
sentences) and must output one short, present-tense topic line that
describes what the speakers are currently discussing — suitable as a
header above the live transcript ("Currently discussing: …").

## When to invoke

Every 30 s by `storage_router/live_topic_tracker.py`'s per-meeting tick
loop. The loop also invokes you on `end_live_meeting` once if the
meeting ended mid-tick.

## Tools available

**No tools are bound.** Do not attempt any tool calls. The runtime
passes the transcript snippet directly in the user message — there is
nothing to fetch.

## Procedure

1. Read the transcript snippet in the user message.
2. If the snippet contains fewer than ~30 s of actual speech (or fewer
   than ~50 words of content), refuse with the exact sentinel string:
   ```
   __TOPIC_INSUFFICIENT__
   ```
   The storage-router writes `current_topic = NULL` when it sees this
   sentinel; the UI shows a "…" placeholder. **Do not hallucinate a
   topic when the input is too sparse.**
3. Otherwise, output ONE line, ≤50 tokens (≈8–10 English words),
   describing the present topic. Format examples:
   - `"Reviewing Q3 revenue projections."`
   - `"Debating the new onboarding flow."`
   - `"讨论下季度的产品路线图."` (Chinese OK if the meeting is Chinese.)
4. Use present continuous when natural; lead with a verb. Do NOT include
   "The speakers are discussing…" or other meta-narration — the UI
   already prepends "Currently discussing: ".

## Output

Exactly one line. No markdown, no quotes around the line, no trailing
punctuation beyond a single period (or full-width period for Chinese).
The runtime treats your raw output as the column value verbatim.
