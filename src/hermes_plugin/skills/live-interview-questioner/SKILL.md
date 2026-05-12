# Skill: live-interview-questioner

## Purpose

The storage-router invokes this skill every 60 s while an interview meeting is
`live`. You receive the interviewee's name, their role/topic, and the
transcript of the meeting so far. You must output 3–5 concise questions the
human interviewer should consider asking next, grounded in what has already
been said and — if prior workspace context is available — in prior meetings
involving this person.

## When to invoke

Every 60 s by `storage_router/live_interview_questioner.py`'s per-meeting tick
loop. Only invoked when the meeting's `interviewee_name IS NOT NULL` (regular
meetings skip this skill entirely).

## Tools available

- `get_meeting_transcript` — fetch the full transcript for this meeting.
- `search_workspace_cards` — search memory cards across all meetings by keyword
  (use `interviewee_name` as the query to retrieve prior context).
- `search_workspace_transcripts` — search speaker-segment text across all
  meetings by keyword.

**Do NOT call** `create_draft_memory_card` or any write-side tool. This skill
is read-only; it observes and proposes, never persists.

## Procedure

1. Call `get_meeting_transcript` to read the conversation so far.
2. Optionally call `search_workspace_cards` and/or
   `search_workspace_transcripts` with the interviewee's name to retrieve prior
   context. If the searches return nothing, proceed with only the live
   transcript — do not hallucinate prior context.
3. Output 3–5 concise, actionable interview questions the interviewer should
   consider asking next. Each question must be grounded in something actually
   said or discovered (the transcript, prior cards, etc.). Do **not** include
   generic filler questions.
4. If you cited a prior meeting via `search_workspace_cards` or
   `search_workspace_transcripts`, append a brief parenthetical: e.g.
   `(from: <meeting title>)`.

## Output format

Return a JSON object with a single key `"questions"` whose value is a JSON
array of 3–5 strings. Each string is one complete question. No other keys.

```json
{
  "questions": [
    "Can you elaborate on the tradeoffs you mentioned between X and Y?",
    "What does success look like for this initiative in 6 months?",
    "You said Z was blocked — what would unblock it?"
  ]
}
```

The storage-router parses `final_text` as JSON, extracts `questions`, and
writes the list (capped at 5) to `meetings.suggested_questions`. If the
transcript is too sparse to generate meaningful questions (fewer than ~50
words), return an empty array: `{"questions": []}`.
