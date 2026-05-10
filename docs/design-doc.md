# Design Doc: Hermes-Powered Meeting Memory Tracker

## 1. Product summary

**Tracker** is a real-time meeting-memory assistant powered by Hermes Agent.

It captures live meetings, reads stabilized transcript chunks during the meeting, dynamically determines the meeting type and output structure, creates draft meeting memory in real time, and finalizes evidence-backed memory after the meeting ends.

It also supports importing past conversations through a unified **Import Existing Conversation** entrance, where users can upload either:

```text
raw voice file
or
text transcript file / pasted transcript
```

Both paths eventually become the same normalized transcript object.

---

## 2. Product inspiration from mature tools

The mature products in this category show several patterns worth borrowing:

**Otter** supports importing audio/video files and automatically transcribing them into searchable/shareable text, so imported voice files should be treated as first-class meeting inputs, not a secondary utility. ([Otter Help Center][1])

**Fireflies** says uploads get the same analysis as live meetings: full transcription, summaries, and insights. That is the right product principle for Tracker: imported raw voice files and transcript files should pass through the same analysis pipeline after normalization. ([Fireflies][2])

**Fathom** emphasizes global search across an organization's meeting library, real-time collaboration, key-moment tagging, and custom meeting summary templates. Tracker should borrow the "meeting library + key moments + searchable memory" idea, but let Hermes dynamically generate the meeting structure instead of forcing a fixed template. ([Fathom AI][3])

**Granola** emphasizes bot-free audio capture, customizable meeting formats, and AI-enhanced notes based on transcripts and user notes. Tracker should borrow the editable note workflow and flexible meeting structure, while using Hermes as the assistant and memory curator. ([Granola][4])

For Zoom, the preferred live path should be **Zoom RTMS**, because the Zoom RTMS SDK supports real-time audio, video, and transcript streams from Zoom Meetings and lets developers process live meeting streams and participant/session events. ([GitHub][5])

---

## 3. Goals and non-goals

### Goals

Tracker should:

```text
1. Capture live raw voice meetings.
2. Capture live Zoom meetings.
3. Let users import existing raw voice files.
4. Let users import text transcript files or pasted transcripts.
5. Normalize all inputs into one meeting transcript format.
6. Let Hermes process stable transcript chunks during live meetings.
7. Let Hermes dynamically infer the meeting type and structure.
8. Generate live draft notes and draft memory cards.
9. Finalize meeting notes and memory after the meeting ends.
10. Let users ask Hermes questions during and after meetings.
11. Store evidence-backed meeting memory with transcript timestamps.
```

### Non-goals for MVP

Do not build these in the first version:

```text
Slack Huddles
Google Meet
Microsoft Teams
repo monitoring
Jira / Linear automation
project health scoring
complex project dashboard
autonomous ticket creation
Hermes self-evolution pipeline
```

The product should remain a **meeting-memory assistant**, not a full project-management system.

---

## 4. Final MVP input model

### Primary input paths

```text
A. Live raw voice input
   - browser microphone
   - desktop microphone
   - meeting-room microphone

B. Live Zoom input
   - Zoom RTMS preferred
   - Zoom transcript/recording fallback

C. Import existing conversation
   - raw voice file
   - transcript file
   - pasted transcript
```

### Key revision: shared import entrance

The product should have one import entrance:

```text
Import Existing Conversation
  ├── Upload voice file
  ├── Upload transcript file
  └── Paste transcript text
```

The UI should not create separate product areas for "voice file" and "transcript." They are both existing conversations.

The backend routes them differently at first, but downstream they become the same object.

```text
Raw voice file
  → speech-to-text
  → diarization
  → normalized transcript
  → chunking
  → Hermes extraction
  → meeting memory

Text transcript
  → transcript parser
  → normalized transcript
  → chunking
  → Hermes extraction
  → meeting memory
```

Once normalized, both paths use the same memory pipeline.

---

## 5. Product surfaces

### 5.1 Live Meeting Console

Primary interface for real-time capture.

```text
Left panel:
  live transcript
  speaker labels
  timestamps
  diarization confidence

Center panel:
  running summary
  current topic
  detected meeting pattern
  dynamic note structure

Right panel:
  draft memory cards
  possible decisions
  possible action items
  open questions
  Ask Hermes
```

Live controls:

```text
Start capture
Pause capture
Stop meeting
Correct speaker
Pin moment
Mark as decision
Mark as action item
Ask Hermes
```

### 5.2 Import Existing Conversation

Single entrance for voice files and transcripts.

```text
Import Existing Conversation

Input options:
  [ Upload voice file ]
  [ Upload transcript file ]
  [ Paste transcript ]

Metadata:
  title
  participants, optional
  date/time, optional
  labels, optional
  visibility
```

After import, the system shows the same processing status page.

For voice file:

```text
1. File uploaded
2. Transcription running
3. Diarization running
4. Transcript normalized
5. Hermes extracting meeting memory
6. Meeting ready
```

For transcript:

```text
1. Transcript received
2. Transcript parsed
3. Transcript normalized
4. Hermes extracting meeting memory
5. Meeting ready
```

### 5.3 Meeting Review Page

Post-meeting canonical page.

```text
Meeting title
source type
detected meeting pattern
participants
labels
evidence quality
sharing state

Tabs:
  Summary
  Transcript
  Memory Cards
  Ask Hermes
  Share / Export
```

### 5.4 Memory Search

Global meeting memory search.

```text
Ask across meetings:
  "What did users say about onboarding?"
  "What did we decide about pricing?"
  "Show action items from last week."
  "Find meetings where OAuth was discussed."
```

Every answer should include transcript evidence.

---

## 6. Core system architecture

```text
┌──────────────────────────────────────────────────────────────┐
│                         Input Layer                          │
│                                                              │
│  Live raw voice | Zoom RTMS | Import voice file/transcript    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    Conversation Gateway                       │
│                                                              │
│  Creates ConversationArtifact                                │
│  Routes source to stream processor, STT, or transcript parser │
└──────────────────────────────┬───────────────────────────────┘
                               │
        ┌──────────────────────┴──────────────────────┐
        │                                             │
        ▼                                             ▼
┌───────────────────────┐                  ┌───────────────────────┐
│ Audio Processing       │                  │ Transcript Processing  │
│ STT + diarization      │                  │ VTT/SRT/TXT/parser     │
│ live or file-based     │                  │ speaker/timestamp parse│
└───────────┬───────────┘                  └───────────┬───────────┘
            │                                          │
            └──────────────────────┬───────────────────┘
                                   ▼
┌──────────────────────────────────────────────────────────────┐
│                    Normalized Transcript                      │
│                                                              │
│  speaker turns | timestamps | confidence | source metadata    │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                 Transcript Stabilizer / Chunker               │
│                                                              │
│  live interim → final chunks                                  │
│  imported transcript → static chunks                          │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                    Meeting Memory Backend                     │
│                                                              │
│  transcripts | chunks | embeddings | memory cards             │
│  summaries | evidence links | permissions | audit logs         │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                 Hermes Meeting Memory Plugin                  │
│                                                              │
│  search chunks | create draft cards | finalize memory         │
│  update schema | answer meeting questions                     │
└──────────────────────────────┬───────────────────────────────┘
                               │
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                  Hermes Live Meeting Assistant                │
│                                                              │
│  dynamic meeting recognition                                  │
│  dynamic extraction schema                                    │
│  live draft memory                                            │
│  final consolidation                                          │
│  Q&A                                                          │
└──────────────────────────────────────────────────────────────┘
```

---

## 7. Hermes role in the MVP

Hermes should be included from the initial version, but with clear boundaries.

### Hermes owns

```text
meeting reasoning
dynamic meeting-type recognition
dynamic schema generation
draft memory card creation
meeting Q&A
post-meeting finalization
assistant behavior
follow-up drafting
```

### Backend owns

```text
audio streaming
voice file upload
Zoom RTMS connection
STT
diarization
transcript parsing
chunking
database storage
vector search
permissions
evidence links
raw artifacts
```

Hermes should not store full transcripts in its built-in memory. Hermes memory is useful for compact preferences and durable assistant behavior, while external meeting memory should live in the product backend. Hermes supports plugins for adding custom tools without modifying core code, and those plugins can expose meeting-memory tools to the agent. ([Hermes Agent][6])

If later you want meeting memory to be automatically prefetched into Hermes context, implement a Hermes **Memory Provider Plugin**. Hermes' memory provider plugin interface is designed for persistent cross-session knowledge beyond built-in `MEMORY.md` and `USER.md`, with hooks such as `prefetch`, `sync_turn`, `on_session_end`, and `on_memory_write`. ([Hermes Agent][7])

For MVP, use a normal Hermes plugin first. Add a memory provider later.

### 7.1 Deployment options

Three candidate deployment modes for Hermes. The MVP default is **sidecar service** unless explicitly changed.

```text
embedded library:
  Hermes runs in-process inside the Tracker backend.
  Pros: lowest latency, no network hop, simplest dev setup.
  Cons: backend and Hermes must share a runtime/language, harder to scale Hermes independently,
        the /api/hermes/* endpoints in §17 collapse into in-process function calls.

sidecar service (MVP default):
  Hermes runs as a separate process/container alongside the backend.
  Pros: independent scaling, language-agnostic, /api/hermes/* endpoints stay HTTP,
        Hermes plugin can talk to backend over the same surface in §17.
  Cons: requires service discovery + auth between backend and Hermes,
        adds one network hop per tool call.

Nous-hosted SaaS:
  Hermes runs in Nous Research's managed infrastructure.
  Pros: zero ops, fastest to start.
  Cons: meeting transcripts leave the workspace boundary, conflicts with §19 privacy defaults,
        not suitable for MVP unless an enterprise tier is offered.
```

Phase 0 closes by confirming the sidecar default (or selecting an alternative). This decision determines whether §17's `/api/hermes/*` endpoints are real HTTP routes or in-process calls.

---

## 8. Unified input object

Every input creates a `ConversationArtifact`.

```json
{
  "artifact_id": "art_123",
  "workspace_id": "ws_001",
  "source_type": "live_voice | zoom_rtms | voice_file | transcript_file | pasted_transcript",
  "capture_mode": "live | imported",
  "title": "Auth Migration Discussion",
  "created_by": "user_001",
  "created_at": "2026-05-10T10:00:00-07:00",
  "visibility": "private",
  "labels": ["Auth Migration"],
  "processing_status": "received"
}
```

Then the artifact becomes a meeting.

```json
{
  "meeting_id": "m_123",
  "artifact_id": "art_123",
  "status": "live | processing | ready | finalized | failed",
  "detected_pattern": null,
  "current_schema": null,
  "evidence_quality": "unknown"
}
```

---

## 9. Normalized transcript format

All input paths must produce this same format.

```json
{
  "meeting_id": "m_123",
  "segments": [
    {
      "segment_id": "seg_001",
      "speaker_id": "speaker_1",
      "speaker_name": "Alice",
      "start_ms": 142300,
      "end_ms": 148900,
      "text": "I think we should delay the provider switch until staging secrets are ready.",
      "confidence": 0.93,
      "source_type": "voice_file",
      "is_final": true
    }
  ]
}
```

For transcript-only input without timestamps:

```json
{
  "segment_id": "seg_001",
  "speaker_id": "unknown",
  "speaker_name": null,
  "start_ms": null,
  "end_ms": null,
  "text": "Team agreed to delay the provider switch until staging secrets are ready.",
  "confidence": null,
  "source_type": "pasted_transcript",
  "is_final": true
}
```

Evidence quality:

```text
high:
  timestamped transcript with speaker labels

medium:
  timestamped transcript without speaker labels

low:
  transcript with speakers but no timestamps

lowest:
  plain notes/transcript without timestamps or speakers
```

---

## 10. Real-time processing design

### 10.1 Live voice input

```text
audio frame
  ↓
streaming STT
  ↓
diarization
  ↓
interim transcript for UI
  ↓
final speaker turns
  ↓
stable chunk
  ↓
Hermes live update
```

Deepgram's diarization recognizes speaker changes and assigns a speaker to each word; its docs distinguish pre-recorded and live-streaming diarization outputs. ([Deepgram Docs][8])

### 10.2 Live Zoom input

```text
Zoom RTMS webhook
  ↓
RTMS client joins meeting stream
  ↓
audio/transcript events received
  ↓
speaker/session metadata attached
  ↓
stable chunks created
  ↓
Hermes live update
```

Zoom's RTMS SDK supports connecting to live Zoom meetings, processing real-time audio/video/transcript streams, and receiving session/participant update events. ([GitHub][5])

### 10.3 Stable chunk rules

Hermes should not process every word.

Recommended chunk triggers:

```text
30–90 seconds of finalized transcript
or
topic boundary detected
or
user pins a moment
or
likely decision/action item appears
or
meeting ends
```

---

## 11. Imported conversation design

### 11.1 Import voice file

```text
User uploads audio file
  ↓
backend stores file
  ↓
batch STT + diarization
  ↓
normalized transcript
  ↓
chunking
  ↓
Hermes extraction
  ↓
meeting review page
```

### 11.2 Import transcript file or pasted transcript

```text
User uploads/pastes transcript
  ↓
parser detects format
  ↓
speaker/timestamp extraction if possible
  ↓
normalized transcript
  ↓
chunking
  ↓
Hermes extraction
  ↓
meeting review page
```

Supported import formats:

```text
audio:
  mp3, wav, m4a, webm, ogg

transcript:
  txt, md, vtt, srt, json
```

The product principle: **voice-file imports and transcript imports get the same downstream analysis as live meetings**, following the mature pattern used by Fireflies. ([Fireflies][2])

---

## 12. Dynamic meeting recognition and schema generation

Meeting-type handling should not be fixed.

Hermes should infer a **meeting pattern**:

```json
{
  "primary_pattern": "customer_discovery_call",
  "secondary_patterns": ["product_planning", "implementation_discussion"],
  "interaction_style": "interview_with_internal_discussion",
  "confidence": 0.87,
  "reason": "Most of the first half is user feedback, followed by internal product planning."
}
```

Then Hermes selects **extraction blocks**:

```json
{
  "selected_blocks": [
    "summary",
    "topics",
    "user_pain_points",
    "direct_quotes",
    "feature_requests",
    "objections",
    "requirements",
    "follow_ups",
    "open_questions"
  ]
}
```

Do not hard-code templates like:

```text
group sync
user interview
group discussion
```

Instead, define reusable extraction blocks:

```text
summary
topics
decisions
action_items
open_questions
risks
blockers
progress_updates
requirements
user_pain_points
user_quotes
feature_requests
objections
tradeoffs
alternatives_considered
technical_details
customer_signals
follow_ups
next_steps
```

Hermes assembles the meeting structure from these blocks.

This is more flexible than fixed templates, while still giving users consistent outputs.

### 12.1 Phasing

The §12 spec is the *full* surface. Two phased subsets:

```text
Phase 2 (basic):
  pattern object:
    primary_pattern + confidence only
    secondary_patterns omitted
    interaction_style omitted
    reason omitted
  block selection:
    fixed set of 6 blocks:
      summary, topics, decisions, action_items, open_questions, follow_ups
  trigger:
    runs once on imported transcript after extraction
    no live updates

Phase 4 (full):
  pattern object:
    add secondary_patterns, interaction_style, reason
  block selection:
    open the full 19-block library
    Hermes picks blocks dynamically per meeting
  trigger:
    re-runs on every stable chunk during a live meeting
    re-runs at finalization
```

Phase 2 exit criteria reference this subset; Phase 4 exit criteria reference the full surface.

---

## 13. Memory card model

Hermes should create draft memory cards during live processing and final memory cards after post-meeting consolidation.

```json
{
  "memory_card_id": "mem_456",
  "meeting_id": "m_123",
  "state": "candidate | draft | committed | rejected",
  "type": "decision | action_item | pain_point | quote | requirement | risk | open_question | technical_detail",
  "title": "Empty dashboard after signup causes confusion",
  "content": "The user expected guidance after signup but found an empty dashboard.",
  "source_chunk_ids": ["chunk_008"],
  "source_start_ms": 360000,
  "source_end_ms": 372000,
  "speakers": ["Dana"],
  "confidence": 0.91,
  "needs_review": true
}
```

Memory states:

```text
candidate:
  detected live, uncertain

draft:
  evidence-backed but not final

committed:
  finalized after meeting

rejected:
  dismissed by user or finalizer
```

---

## 14. Hermes plugin design

Create a plugin:

```text
hermes/plugins/live-meeting-memory/
├── plugin.yaml         # plugin manifest
├── __init__.py         # plugin entry point, registers tools
├── schemas.py          # JSON-schema definitions for each tool
├── tools.py            # tool implementations; thin wrappers that call client.py
└── client.py           # HTTP client for the /api/hermes/* surface in §17
                        # In sidecar mode (§7.1 default) it speaks HTTP.
                        # In embedded mode this file collapses to direct function imports.
```

Hermes plugin docs show that plugins can add custom tools, hooks, and integrations without changing Hermes core, and a plugin directory typically includes `plugin.yaml`, `__init__.py`, `schemas.py`, and `tools.py`. ([Hermes Agent][6]) `client.py` is a Tracker-specific addition that isolates the backend transport so `tools.py` stays pure.

### Plugin tools

```text
get_live_meeting_state
get_recent_transcript_chunks
get_meeting_transcript
search_meeting_memory
search_memory_cards
update_meeting_pattern
update_dynamic_schema
create_draft_memory_card
update_draft_memory_card
commit_memory_card
reject_memory_card
get_transcript_evidence
finalize_meeting_memory
answer_from_meeting_memory
```

### Example tool schema

```json
{
  "name": "create_draft_memory_card",
  "description": "Create a draft memory card from a live or imported meeting. Use only when transcript evidence supports the memory.",
  "parameters": {
    "type": "object",
    "properties": {
      "meeting_id": { "type": "string" },
      "type": {
        "type": "string",
        "description": "AI-determined memory type, such as decision, action_item, pain_point, quote, requirement, risk, or open_question."
      },
      "title": { "type": "string" },
      "content": { "type": "string" },
      "source_chunk_ids": {
        "type": "array",
        "items": { "type": "string" }
      },
      "confidence": { "type": "number" },
      "needs_review": { "type": "boolean" }
    },
    "required": ["meeting_id", "type", "title", "content", "source_chunk_ids", "confidence"]
  }
}
```

---

## 15. Hermes skills

Create these skills from MVP:

```text
live-meeting-analysis
dynamic-meeting-schema
meeting-memory-extraction
meeting-finalization
meeting-qa
follow-up-drafting
```

### `live-meeting-analysis/SKILL.md`

Purpose:

```text
When reading stable transcript chunks during a live meeting:
- update the meeting pattern
- update the running summary
- detect possible decisions, actions, questions, insights
- never commit memory during live processing
- mark uncertain items as candidate
- cite source chunks
```

### `meeting-finalization/SKILL.md`

Purpose:

```text
After the meeting ends:
- re-read full transcript
- finalize meeting pattern
- finalize selected extraction blocks
- merge duplicate draft memory cards
- verify each memory card against evidence
- downgrade unsupported claims
- create final meeting note
```

### `meeting-qa/SKILL.md`

Purpose:

```text
When answering meeting questions:
- search memory cards first
- then summaries
- then transcript chunks
- cite evidence
- say when evidence is weak
- avoid inventing owners, dates, or decisions
```

---

## 16. Database design

### Core tables

```text
workspaces
users
conversation_artifacts
meetings
meeting_sources
participants
speaker_segments
transcript_chunks
meeting_patterns
dynamic_schemas
memory_cards
meeting_notes
shares
audit_logs
```

### `conversation_artifacts`

```sql
id
workspace_id
source_type
capture_mode
title
created_by
created_at
raw_file_url
raw_text
processing_status
visibility
```

### `meetings`

```sql
id
artifact_id
status
started_at
ended_at
detected_pattern
current_schema
evidence_quality
finalized_at
```

### `speaker_segments`

```sql
id
meeting_id
speaker_id
speaker_name
start_ms
end_ms
text
confidence
source_type
is_final
```

### `transcript_chunks`

```sql
id
meeting_id
start_ms
end_ms
text
speaker_turns_json
is_final
processed_by_hermes
created_at
```

### `memory_cards`

```sql
id
meeting_id
state
type
title
content
source_chunk_ids
source_start_ms
source_end_ms
speakers_json
confidence
needs_review
created_by_agent
created_at
updated_at
```

---

## 17. API design

### Input APIs

```http
POST /api/conversations/import
```

Accepts:

```text
voice file
transcript file
pasted transcript
```

```http
POST /api/live-meetings/start
POST /api/live-meetings/{id}/audio-frame
POST /api/live-meetings/{id}/stop
```

```http
POST /api/zoom/rtms/webhook
```

### Meeting APIs

```http
GET /api/meetings/{id}
GET /api/meetings/{id}/transcript
GET /api/meetings/{id}/chunks
GET /api/meetings/{id}/memory-cards
POST /api/meetings/{id}/finalize
```

### Memory APIs

```http
POST /api/memory-cards
PATCH /api/memory-cards/{id}
POST /api/memory-cards/{id}/commit
POST /api/memory-cards/{id}/reject
```

### Search / Q&A APIs

```http
POST /api/search/meetings
POST /api/qa/meeting
POST /api/qa/global
```

### Hermes-facing APIs

```http
GET /api/hermes/live-meetings/{id}/state
GET /api/hermes/meetings/{id}/recent-chunks
POST /api/hermes/meetings/{id}/pattern
POST /api/hermes/meetings/{id}/schema
POST /api/hermes/memory-cards
POST /api/hermes/meetings/{id}/finalize
```

---

## 18. UX design

### 18.1 Home

```text
Live meetings
Imported conversations
Recently finalized meetings
Needs review
Search meeting memory
```

### 18.2 Start Live Meeting

```text
Start Live Meeting

Source:
  [ Raw voice ]
  [ Zoom ]

Options:
  title
  visibility
  expected participants
  labels
```

### 18.3 Import Existing Conversation

```text
Import Existing Conversation

Drop file or paste transcript

Supported:
  audio file
  transcript file
  pasted transcript

The system will detect the input type automatically.
```

This is the key UX change.

### 18.4 Processing View

```text
Conversation received
Input detected: voice file
Transcription: running
Diarization: running
Transcript normalization: waiting
Hermes analysis: waiting
```

or:

```text
Conversation received
Input detected: transcript text
Transcript parsing: running
Hermes analysis: waiting
```

### 18.5 Live Meeting Console

```text
Transcript
Running summary
Detected structure
Draft memory cards
Ask Hermes
```

### 18.6 Post-meeting Review

```text
Detected pattern:
  Customer discovery + product planning

Generated structure:
  Summary
  Pain points
  Quotes
  Feature requests
  Decisions
  Follow-ups

Memory cards:
  Approve / Edit / Reject
```

---

## 19. Privacy and safety requirements

Meeting memory products are sensitive. The design should default to conservative sharing.

Minimum requirements:

```text
private by default
explicit sharing
workspace-level access control
audit logs
delete/export controls
recording consent setting
retention policy
no public-by-link default
no AI-training opt-in by default
```

This matters because the product stores long-term conversation memory, not just summaries.

---

## 20. Evaluation criteria

### Transcription quality

```text
word error rate
speaker diarization accuracy
speaker-name correction rate
timestamp accuracy
```

### Hermes memory quality

```text
memory card precision
memory card recall
unsupported-claim rate
decision/action-item extraction accuracy
evidence citation accuracy
duplicate card rate
```

### User experience

```text
time to useful live summary
time to finalized meeting note
review burden
search success rate
percentage of answers with evidence
```

### System quality

```text
live stream latency
chunk processing latency
STT failure rate
Hermes tool-call failure rate
finalization failure rate
```

---

## Final revised concept

```text
Tracker = Hermes-powered live meeting memory assistant

Inputs:
  live raw voice
  live Zoom
  imported voice file
  imported transcript

Core pipeline:
  capture/import
  → normalize transcript
  → chunk
  → Hermes analyzes
  → dynamic meeting structure
  → draft memory
  → final verified memory
  → searchable Q&A
```

The most important product rule:

> **All inputs become the same normalized meeting memory object.**
> Live meetings, raw voice files, and text transcripts differ only before normalization. After normalization, Hermes treats them the same.

---

## References

[1]: https://help.otter.ai/hc/en-us/articles/360047733574-Import-an-audio-or-video-file "Otter Help Center — Import an audio or video file"
[2]: https://guide.fireflies.ai/articles/3893959957-learn-about-the-uploads-feature-in-fireflies "Fireflies Knowledge Base — Upload audio and video files"
[3]: https://www.fathom.ai/overview "Fathom — Overview"
[4]: https://www.granola.ai/ "Granola — The AI Notepad for back-to-back meetings"
[5]: https://github.com/zoom/rtms/blob/main/README.md "Zoom RTMS — README"
[6]: https://hermes-agent.nousresearch.com/docs/user-guide/features/plugins "Hermes Agent — Plugins"
[7]: https://hermes-agent.nousresearch.com/docs/developer-guide/memory-provider-plugin "Hermes Agent — Memory Provider Plugins"
[8]: https://developers.deepgram.com/docs/diarization "Deepgram — Speaker Diarization"
