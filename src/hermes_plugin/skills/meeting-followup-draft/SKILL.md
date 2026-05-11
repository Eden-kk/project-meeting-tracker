# Skill: meeting-followup-draft

## Purpose

Draft a follow-up email after a meeting. The output is a markdown body
the user can copy into their email client. The skill MUST stay
grounded in the meeting's memory cards + transcript; it MUST NOT invent
owners, dates, or commitments.

## When to invoke

The user clicks "Draft follow-up" on a finalized meeting's Memory Cards
tab. The orchestrator passes `meeting_id` and optionally `recipient`
(a free-text name; already sanitized to alphanumeric + space + hyphen
+ apostrophe by the route, max 100 chars) and `tone` ∈ {decisive,
warm, neutral}. Default tone is `neutral`.

## Tools available

Only these two tools are bound:
- `search_memory_cards` — pull the meeting's visible cards (any type).
- `get_meeting_transcript` — fall back when a claim needs verbatim
  context.

## Procedure

1. Call `search_memory_cards(meeting_id=<id>)` and read every card.
   Categorize them in your head: decisions, action items, open
   questions, risks, requirements.
2. If two or more cards conflict, prefer the higher `confidence`
   card. If both are high-confidence and conflicting, surface the
   conflict as an open question rather than picking one.
3. Compose a markdown body with these sections (omit any section
   that has no content):
   - **Greeting line.** Use the recipient's name if provided; else
     "Hi team,".
   - **One-sentence recap** of the meeting's purpose.
   - **Decisions** — bulleted; one bullet per decision card.
   - **Action items** — bulleted; one bullet per action_item card.
     Format: `- [Owner] Task — due <date if cited, else "TBD">`.
   - **Open questions / next steps** — bulleted; one bullet per
     open_question card.
   - **Closing line** matching the requested tone.
4. NEVER invent an owner, deadline, or commitment that is not in a
   card or transcript segment. If a date is unclear, write "TBD".

## Tone guide

- `decisive` — short sentences, imperative voice, no hedging.
- `warm` — friendlier connectors ("thanks for the great discussion"),
  still no fluff.
- `neutral` (default) — flat, factual, professional.

## Output contract

Return EXACTLY this JSON, with no surrounding prose:

```
{
  "markdown": "<the full follow-up body as one markdown string>",
  "cards_referenced": ["<memory_card_id>", ...]
}
```

`cards_referenced` lists every card you drew from. If the meeting has
no cards yet, return a one-line markdown body that says exactly:
`This meeting has no memory cards yet; nothing to follow up on.` and an
empty `cards_referenced` array.
