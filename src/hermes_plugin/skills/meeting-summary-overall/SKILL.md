# Skill: meeting-summary-overall

## Purpose

After per-chunk extraction completes, write ONE coherent narrative
summary of the meeting that the SPA's Summary tab renders as markdown.
The output complements — does NOT duplicate — the Decisions / Action
Items / Open Questions / Pain Points / etc. memory cards already
extracted from the same meeting (those have their own tabs).

## When to invoke

Once per finalize, after every chunk has finished extracting cards.

## Tools available

**No tools are bound.** Do not attempt any tool calls; the runtime
ignores any `tool_use` blocks for this skill.

## Input

The user message is the per-chunk topic sentences, one per line. They
are NOT prefixed with `"Chunk N/M:"` — treat them as a flat ordered list
of beats from the meeting.

## Output contract

Return ONLY markdown, exactly three sections in this order. No preamble,
no closing remarks, no fenced code block around the output.

```
## TL;DR
{ONE sentence, <=30 words. Plain English. Answers "what was this meeting
about and what came out of it?" The version someone reads in 10 seconds.}

## What we covered
{2-4 short paragraphs of narrative arc. Tells the story of how the
conversation flowed: what opened it, the central topic(s), where the
group converged or disagreed, and any context needed for someone who
wasn't there. Names people. Plain prose. Do NOT include bulleted lists
of decisions, action items, open questions, requirements, or risks —
those live in their own tabs and the user explicitly does not want
duplication here.}

## Notes
{Free-form. Anything important that doesn't belong in the narrative:
notable quotes, edge cases flagged but unresolved, sensitive-content
callouts, follow-up meetings mentioned, recording gaps. OPTIONAL —
omit the entire `## Notes` section (heading and all) if there's
nothing worth flagging. Do not write a placeholder.}
```

## Style rules

- Markdown headings only (`##`). Do not use `###` or deeper. Do not use
  `#` (the SPA renders the meeting title separately).
- Use names for people whenever the topic sentences provide them; never
  invent attendee names.
- Use plain English. No unexplained acronyms unless they appear in the
  topic sentences themselves.
- Favor clarity over completeness — if the topic sentences don't cover
  something, don't speculate.
- The total summary length should be roughly 150-300 words. Tighter is
  better.

## Failure modes

- Empty / "no findings" topic sentences only -> return exactly:
  `## TL;DR\nMeeting had no extractable content (silence, small talk, or recording gap).`
  and nothing else.
- Conflicting beats from different chunks -> describe the conflict in the
  narrative; do not pick a winner.
- **Card-meta beats in the input** (lines like "Created 3 cards covering
  …", "Identified 2 open questions", "Extracted a decision and an action
  item"). These are bugs in the upstream chunk skill — they describe
  bookkeeping, not the meeting. Strip the meta phrasing and recover any
  embedded content. "Created 3 cards covering a decision to ship Friday
  and an action item for Bob" should become "The team decided to ship
  Friday and Bob took an action item." If a topic sentence is PURELY
  meta with no recoverable content (e.g. "Created 5 cards covering
  decisions and action items"), drop it from your narrative — don't
  echo it back. Never write a TL;DR or What-we-covered section that
  talks about how many cards were created; the user cannot see that
  and does not care.
- **Refusal JSON / text in the input** (lines like
  `{"refused": true, "reason": "transcript_too_large"}` or English
  refusal text like "The transcript is over 100,000 tokens"). These
  are the upstream chunk skill failing. Treat them as missing beats —
  do not echo them in your output. If ALL chunks produced refusals,
  fall back to the empty-content failure mode above.
