# Development Roadmap: Hermes-Powered Meeting Memory Tracker

> Companion to [design-doc.md](./design-doc.md). No calendar estimates; this is a sequencing roadmap with clear exit criteria.

## Skill → Phase map

The 6 Hermes skills defined in design-doc §15 ship across the roadmap as follows:

```text
meeting-memory-extraction   Phase 2
meeting-finalization        Phase 2
meeting-qa                  Phase 2
live-meeting-analysis       Phase 4
dynamic-meeting-schema      Phase 4
follow-up-drafting          Phase 7
```

Phase 2 covers the imported-conversation path; live-only skills are deferred to Phase 4.

---

## Phase 0 — Product and architecture foundation

### Build

```text
finalize input scope
define ConversationArtifact model
define NormalizedTranscript model
define MemoryCard model
define extraction block library
choose STT/diarization provider
choose vector store
choose Hermes deployment mode
```

### Exit criteria

```text
input model is stable
database schema draft is approved
Hermes plugin tool list is approved
live vs imported flows are clearly separated but converge after normalization
```

---

## Phase 1 — Shared import path MVP

Focus: raw voice file and text transcript share one entrance.

### Build

```text
Import Existing Conversation UI
voice file upload
transcript file upload
paste transcript
artifact router
batch STT for voice files
transcript parser
normalized transcript storage
basic meeting review page
```

### Why this phase first

It validates the core memory pipeline without needing real-time streaming complexity.

### Exit criteria

```text
user can upload a voice file
user can upload/paste a transcript
both produce normalized transcript segments
both produce the same meeting review page
  Phase-1 scope:
    Summary tab (placeholder, populated in Phase 2)
    Transcript tab (full)
  Deferred:
    Memory Cards tab    → Phase 2
    Ask Hermes tab      → Phase 7
    Share / Export tab  → Phase 8
```

---

## Phase 2 — Hermes extraction MVP

Focus: Hermes becomes the assistant and memory curator.

### Build

```text
Hermes profile: meeting-tracker
Hermes plugin: live-meeting-memory
tools:
  get_meeting_transcript
  create_draft_memory_card
  search_memory_cards
  finalize_meeting_memory

skills:
  meeting-memory-extraction
  meeting-finalization
  meeting-qa
  (live-meeting-analysis + dynamic-meeting-schema deferred to Phase 4)

basic dynamic pattern recognition  (per design-doc §12.1 Phase-2 subset:
                                    primary_pattern + confidence only)
basic dynamic extraction block selection (per design-doc §12.1 Phase-2 subset:
                                          fixed 6 blocks — summary, topics,
                                          decisions, action_items,
                                          open_questions, follow_ups)
```

### Exit criteria

```text
Hermes can read imported transcript chunks
Hermes can infer meeting pattern
Hermes can generate selected extraction blocks
Hermes can create draft memory cards
Hermes can finalize meeting notes
Hermes can answer questions from meeting memory
```

---

## Phase 3 — Meeting review and memory quality

Focus: make generated memory trustworthy.

### Build

```text
memory card review UI
approve/edit/reject cards
source evidence linking
speaker correction UI
evidence quality indicator
duplicate card merge
confidence scoring
```

### Exit criteria

```text
every memory card links to source transcript/chunk
user can correct speakers
user can approve/edit/reject extracted memory
final meeting memory is searchable
Hermes answers include evidence
```

---

## Phase 4 — Live raw voice MVP

Focus: real-time non-Zoom capture.

### Build

```text
browser mic capture
streaming STT
streaming diarization
interim transcript UI
final transcript turn assembly
stable transcript chunker
Hermes live update worker
live running summary
live draft memory cards
```

### Exit criteria

```text
user can start a live voice meeting
transcript appears live
stable chunks are created
Hermes processes chunks during meeting
draft summary and draft memory cards update live
post-meeting finalization works
```

---

## Phase 5 — Zoom RTMS MVP

Focus: real-time Zoom integration.

### Build

```text
Zoom RTMS app setup
webhook validation
RTMS client
audio/transcript callback handling
participant/session event handling
Zoom meeting source mapping
Zoom live chunks
Zoom fallback transcript import
```

### Exit criteria

```text
Zoom meeting can stream into Tracker
Tracker receives real-time Zoom audio/transcript data
Hermes processes Zoom stable chunks
Zoom meeting finalizes into same meeting review page
```

Zoom RTMS is suitable here because the SDK supports live meeting connection, real-time stream processing, participant/session events, and webhook handling. ([GitHub][5])

---

## Phase 6 — Global meeting memory search

Focus: make the product useful across meetings.

### Build

```text
vector search over transcript chunks
keyword search over transcripts
memory-card search
global Ask Hermes
filters:
  date
  participant
  label
  meeting pattern
  memory type
```

### Exit criteria

```text
user can ask questions across all meetings
answers cite meetings and transcript evidence
Hermes searches memory before answering
search works for imported and live meetings
```

---

## Phase 7 — Assistant behavior and team usage

Focus: make Hermes feel like a useful meeting teammate.

### Build

```text
Ask Hermes in live meeting
Ask Hermes on meeting page
Ask Hermes globally
follow-up email drafting
action-item list
open-question list
private/team sharing
basic notification when meeting is finalized
```

### Exit criteria

```text
Hermes can answer:
  what happened so far?
  what decisions were made?
  what should we follow up on?
  what did users say about X?
  draft a follow-up message
```

---

## Phase 8 — Hardening and production readiness

### Build

```text
retention controls
audit logs
permission enforcement
workspace admin settings
recording consent settings
model/provider fallback
STT failure recovery
Hermes tool-call retries
observability dashboard
eval set for memory extraction quality
```

### Exit criteria

```text
production deployment is safe for real teams
failed transcription jobs can recover
Hermes memory cards can be audited
private meetings remain private
answers are permission-aware
```

---

## Recommended build order

The best order is:

```text
1. Shared import entrance:
   voice file + transcript

2. Hermes extraction:
   dynamic meeting pattern + memory cards

3. Review and evidence:
   speaker correction + approve/edit/reject

4. Live raw voice:
   streaming STT + Hermes live chunks

5. Zoom RTMS:
   real-time Zoom input

6. Global meeting memory:
   Ask Hermes across meetings

7. Production hardening:
   permissions, audit, retention, evals
```

This order gives you the fastest validated MVP while still moving toward the real-time Hermes assistant.

---

## References

[5]: https://github.com/zoom/rtms/blob/main/README.md "Zoom RTMS — README"
