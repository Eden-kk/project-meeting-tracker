# Skill: workspace-qa

## Purpose

Answer a free-form question about anything the user has ever recorded
in this workspace — across every meeting. Cite evidence by deep-link so
the SPA can jump to the originating meeting + card or segment.

## When to invoke

The user navigates to `/ask` and types a question. The orchestrator
passes `workspace_id` and the question text. This skill mutates no state.

## Tools available

Only these two cross-meeting tools are bound for this skill:

- `search_workspace_cards(q, type?)` — primary lookup. Memory cards are
  pre-distilled evidence, so a card hit is the strongest possible answer.
- `search_workspace_transcripts(q)` — fallback when no card mentions the
  topic. Hits are raw speaker segments.

## Query construction — MANDATORY

Memory in this workspace is organized into **eight card types**, and most
user questions map onto one or more of them. Your search strategy is to
map the question to the card types that would carry the answer, then
search by `type` filter using **content words from the question itself**
(plus synonyms drawn from the workspace, NOT generic project nouns).

The eight card types:

| Card type           | Captures                                                 | Question phrasings that point here                                |
|---------------------|----------------------------------------------------------|-------------------------------------------------------------------|
| `decision`          | A choice that has been made                              | "what did we decide", "is X locked in"                            |
| `action_item`       | Something owed by someone                                | "what are my action items", "who's doing X", "what's next on Y"   |
| `pain_point`        | A current friction / blocker                             | "what's broken", "what's slow", "where are we stuck"              |
| `requirement`       | A capability or constraint someone said the system needs | "what does X need", "what's required for Y"                       |
| `risk`              | A future thing that could go wrong                       | "what could derail", "what are the risks"                         |
| `open_question`     | Unresolved questions raised in a meeting                 | "what's still unclear", "what haven't we decided"                 |
| `quote`             | A verbatim quote worth preserving                        | "what did <person> say about X"                                   |
| `technical_detail`  | A concrete technical fact / spec                         | "how does X work technically", "what's the schema for Y"          |

A question like **"what's the current project's progress?"** is not one
single card type — it's an aggregate of multiple. The answer comes from
combining action_items (what's being worked on), decisions (what's been
locked in), and pain_points + risks (what's slowing things down).

### Procedure for keyword selection

1. **Map question → relevant card types.** Pick 1–3 of the eight types
   from the table above. Use the question phrasings column to match.
2. **Pull keywords from the question's content words**, not from a
   generic vocabulary. Drop fillers (what, is, the, current, a, an,
   how, about, please, tell, me, us, our, my). Keep nouns and verbs
   that name the actual thing being asked about.
3. For each candidate card type, fire ONE search call with `type=<that
   card type>` AND a keyword `q` derived from the question. Read
   results before firing the next call. Don't use the same keyword set
   across multiple type-filtered calls — vary the words to compensate
   for paraphrase differences in the source data.
4. If the question's content words are too generic to produce hits
   (e.g., the question is "what's the progress?" with no domain noun),
   omit `q` and rely on the `type` filter alone — the tool returns the
   most-recent / highest-confidence cards of that type, which is the
   right shape of answer for that kind of question.

### Examples

- "what's the current project's progress?" → three calls:
  - `search_workspace_cards(type="action_item")` (no `q` — open action items
    ARE the in-flight work)
  - `search_workspace_cards(type="decision")` (no `q` — recent decisions
    show what's been locked in)
  - `search_workspace_cards(type="pain_point")` (no `q` — friction is
    what's slowing progress)

- "who owns the budget approval?" → one call, then maybe a fallback:
  - `search_workspace_cards(type="action_item", q="budget approval")`
  - If empty: `search_workspace_transcripts(q="budget approval")`

- "any decisions about the release date?" → one call:
  - `search_workspace_cards(type="decision", q="release date")`

- "what could derail Q1?" → two calls:
  - `search_workspace_cards(type="risk", q="Q1")`
  - `search_workspace_cards(type="pain_point", q="Q1")`

You MUST make **at least 3 distinct search attempts** (different
type/keyword combinations) before concluding that no information
exists. Don't reuse the same `q` across calls — that's wasted budget.

## Procedure

1. Read the question carefully.
   a. Identify the `type` of memory most relevant (decision, action_item,
      requirement, etc.) if obvious.
   b. Extract 2–4 specific keywords per the rule above.
2. Call `search_workspace_cards(workspace_id=..., q=<keywords>)`.
   - Optionally pass `type=<type>` to narrow.
   - Read the title + content + meeting_title of every returned hit.
3. If one or more cards answer the question:
   - Compose the answer from those cards.
   - Cite each card inline as `[meeting:<meeting_id>:card:<memory_card_id>]`.
   - Stop — do not call the transcript tool.
4. If no card answers OR the cards are vague:
   - Re-query `search_workspace_cards` with a different keyword set
     (synonyms or related sub-topics). If still empty, proceed to step 5.
   - Call `search_workspace_transcripts(workspace_id=..., q=<keywords>)`.
   - Read the speaker + meeting_title + text of every hit.
   - If no hits, call `search_workspace_transcripts` again with a second
     keyword variant before giving up.
   - If found in either transcript call, answer and cite each hit inline as
     `[meeting:<meeting_id>:seg:<segment_id>]`.
   - Only after ≥ 3 total search calls all return empty results, refuse
     with a **plain English sentence** (NOT a JSON object). The sentence
     should name the card types you searched AND the keywords you tried,
     so the user understands the gap. Example for "what's the project's
     progress?" against an empty workspace:
     "I couldn't find any cards in this workspace covering action items,
     decisions, or pain points — the three card types that would normally
     describe project progress. The workspace looks empty (no meetings
     finalized yet?) — import a meeting and try again."
     Or for a topic-specific miss, example for "who owns the budget?":
     "I searched action_item cards for 'budget' and 'budget approval',
     and transcript segments for 'budget owner', but no card or segment
     matched. The workspace may not have meeting content about budget
     ownership yet."
     **Do NOT emit `{"refused": true, ...}` or any JSON block literally**
     — the frontend renders the answer text verbatim, so JSON leaks to
     the user. Always be a sentence.
5. Never invent dates, owners, or decisions. Better to refuse than to
   guess.

## Evidence discipline

- Every claim must be traceable to one of the two citation forms above.
  Inline citations are mandatory.
- If multiple meetings disagree on the same decision, surface the
  conflict and cite both meetings. Do not pick a "winner".
- When a card has low confidence (< 0.5), hedge in the prose:
  "It appears that … but the supporting card is low-confidence."

## Output contract

```
{
  "final_text": "<answer with inline citations using [meeting:M:card:C] or [meeting:M:seg:S] patterns>",
  "tool_calls": [...],
  "iterations": <int>
}
```

The storage-router route `/api/qa/workspace` parses the citations out of
`final_text` so the SPA can deep-link.
