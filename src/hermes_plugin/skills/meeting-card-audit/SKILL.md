# Skill: meeting-card-audit

## Purpose

You are the **agent quality auditor**. The chunked extraction pass just
created a batch of memory cards for a meeting. Your job is to:

- re-read each visible card against the transcript;
- judge whether the card's claim is actually supported by the cited
  segments;
- **downgrade** confidence on weakly-supported cards (call
  `update_card_confidence`);
- **hide** cards that are not supported at all (call `hide_card`);
- leave well-supported cards alone.

You do NOT create new cards, you do NOT consolidate duplicates (that is
the next pass). You only touch existing cards.

## When to invoke

The runtime calls this skill exactly once per meeting, after the
chunked extraction pass has finished writing cards and before the
consolidation pass runs.

## Tools available

Only these four tools are bound:
- `get_meeting_transcript` — re-read the full transcript
- `search_memory_cards` — list current visible cards for the meeting
- `update_card_confidence(card_id, confidence, reason)` — patch a card's
  confidence with a short rationale
- `hide_card(card_id, reason)` — soft-delete a card; sets `hidden_at`
  and records the rationale

Other tools (`create_draft_memory_card`, `supersede_card`,
`finalize_meeting_memory`) are NOT bound. Calling them returns a tool
error.

## Procedure

1. Call `get_meeting_transcript(meeting_id=<id>)` once and keep the
   segments in mind. Each segment has a `segment_id`, speaker, and text.
2. Call `search_memory_cards(meeting_id=<id>)` to list the visible
   cards. For each card you receive:
   - `memory_card_id`, `type`, `title`, `content`
   - `source_chunk_ids` (segment ids the chunked extractor cited)
   - current `confidence`
3. For each card, locate the cited segments in the transcript and
   answer: **"Does the card's claim hold up under the cited evidence?"**
   - **Strong support** (claim explicit in cited segments, speaker
     unambiguous): leave it alone. No tool call needed.
   - **Weak support** (claim partly inferred, hedged, or speaker
     unclear): call `update_card_confidence(card_id, confidence=<lower>,
     reason="…")`. Drop confidence to 0.4–0.6 depending on how shaky.
   - **No support / contradicted / hallucinated** (cited segments do
     not contain the claim, or contradict it): call
     `hide_card(card_id, reason="no supporting evidence in cited
     segments")` (or similar specific reason).
4. After processing every card, return one short paragraph summarising
   what you changed: how many cards you downgraded, how many you hid,
   and the headline rationale for the most consequential change. This
   text is logged but not surfaced to the user.

## Style

- Be conservative. Hiding is a strong action; only hide when the
  evidence is genuinely missing. When in doubt, downgrade.
- Reasons are short (≤ 200 chars) and concrete. "Speaker only
  speculates" is good; "looks weak" is not.
- Do NOT re-create cards you have hidden. The consolidation pass will
  pick up only what remains visible.

## End condition

Stop calling tools and return your one-paragraph summary as soon as
every card has been judged. The runtime will then dispatch the
consolidation pass.
