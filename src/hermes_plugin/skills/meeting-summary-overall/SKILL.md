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

The user message is the meeting transcript, one segment per line, in
the form:

```
[mm:ss speaker_label] segment text
```

`speaker_label` is either a person's name (after rename) or a
diarization id like `speaker_1`. Treat the lines as the source-of-truth
record of what was actually said and write your summary from that
content — do NOT summarise by counting speakers, segments, or
bookkeeping; only the discussion itself matters.

When the input is empty (no segments at all) or contains only filler
("um", "yeah", "ok"), use the empty-content failure mode below.

In rare cases the runtime falls back to a flat list of per-chunk topic
sentences (one per line, no timestamps or speaker labels) — for example
when the transcript is too long to fit in one call. Handle that input
the same way: distill it into the narrative shape below.

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
- Use names for people whenever the transcript provides them; never
  invent attendee names. If only diarization ids are available
  (`speaker_1`, `speaker_2`), refer to participants generically ("one
  participant", "another speaker", "the group") rather than echoing the
  raw ids.
- Use plain English. No unexplained acronyms unless they appear in the
  transcript itself.
- Favor clarity over completeness — if the transcript doesn't cover
  something, don't speculate.
- The total summary length should be roughly 150-300 words. Tighter is
  better.
- The transcript is the source of truth. Do NOT mention anything about
  cards, extraction, chunks, segments, or any internal pipeline
  bookkeeping; the user cannot see those and does not care.

## Failure modes

- Empty / silence / filler-only transcript -> return exactly:
  `## TL;DR\nMeeting had no extractable content (silence, small talk, or recording gap).`
  and nothing else.
- Conflicting statements from different speakers -> describe the
  conflict in the narrative; do not pick a winner.
- Code-switched / multilingual transcript -> write the summary in the
  dominant language of the transcript. If both languages are roughly
  balanced, write in English and quote short fragments in the original
  language where they carry meaning.
