import { http, HttpResponse } from 'msw';
import type {
  ImportAccepted,
  Meeting,
  MeetingsList,
  NormalizedTranscript,
} from '../api/client';
import type {
  AskHermesResponse,
  EvidenceCitation,
  FinalizeMeetingResponse,
  MemoryCard,
  MemoryCardListResponse,
  MemoryCardState,
  MemoryCardType,
} from '../api/memory_cards.types';
import { expectedNormalized, makeFixtureCards, makeFixtureMeeting } from './fixtures';

type Entry = { meeting: Meeting; createdAt: number; cards: MemoryCard[] };

const meetings = new Map<string, Entry>();
const READY_AFTER_MS = 2000;
let counter = 0;
let cardCounter = 0;

function nextId() {
  counter += 1;
  const stamp = Date.now().toString(36);
  return { meeting_id: `m_${stamp}_${counter}`, artifact_id: `art_${stamp}_${counter}` };
}

function nextCardId(meeting_id: string) {
  cardCounter += 1;
  return `mc_${meeting_id}_new_${cardCounter}`;
}

function currentStatus(entry: Entry): Meeting['status'] {
  return Date.now() - entry.createdAt >= READY_AFTER_MS ? 'ready' : 'processing';
}

function nowIso(): string {
  return new Date().toISOString();
}

function findCardWithEntry(
  cardId: string,
): { card: MemoryCard; entry: Entry } | null {
  for (const entry of meetings.values()) {
    const card = entry.cards.find((c) => c.memory_card_id === cardId);
    if (card) return { card, entry };
  }
  return null;
}

function citationFromSegment(segmentId: string): EvidenceCitation | null {
  const seg = expectedNormalized.segments.find((s) => s.segment_id === segmentId);
  if (!seg) return null;
  return {
    segment_id: seg.segment_id,
    speaker: seg.speaker_name ?? seg.speaker_id ?? 'Unknown',
    start_ms: seg.start_ms ?? 0,
    end_ms: seg.end_ms ?? 0,
    text: seg.text ?? '',
  };
}

export const handlers = [
  http.post('*/api/conversations/import', async ({ request }) => {
    const ids = nextId();
    const form = await request.formData();
    const title = (form.get('title') as string | null) ?? '';
    const meeting = makeFixtureMeeting(ids.meeting_id, ids.artifact_id, title);
    meetings.set(ids.meeting_id, {
      meeting,
      createdAt: Date.now(),
      cards: makeFixtureCards(ids.meeting_id),
    });
    const body: ImportAccepted = {
      artifact_id: ids.artifact_id,
      meeting_id: ids.meeting_id,
      processing_status: 'received',
    };
    return HttpResponse.json(body, { status: 202 });
  }),

  http.get('*/api/meetings', ({ request }) => {
    const url = new URL(request.url);
    const limit = Number(url.searchParams.get('limit') ?? 50);
    const offset = Number(url.searchParams.get('offset') ?? 0);
    // Newest insertion first; mirrors the backend's created_at DESC ordering.
    const all = [...meetings.entries()]
      .sort((a, b) => b[1].createdAt - a[1].createdAt)
      .map(([, entry]) => ({ ...entry.meeting, status: currentStatus(entry) }));
    const body: MeetingsList = {
      items: all.slice(offset, offset + limit),
      total: all.length,
    };
    return HttpResponse.json(body);
  }),

  http.get('*/api/meetings/:id', ({ params }) => {
    const id = params.id as string;
    const entry = meetings.get(id);
    if (!entry) return new HttpResponse(null, { status: 404 });
    const status = currentStatus(entry);
    return HttpResponse.json<Meeting>({ ...entry.meeting, status });
  }),

  http.get('*/api/meetings/:id/transcript', ({ params }) => {
    const id = params.id as string;
    const entry = meetings.get(id);
    if (!entry) return new HttpResponse(null, { status: 404 });
    if (currentStatus(entry) !== 'ready') return new HttpResponse(null, { status: 409 });
    const body: NormalizedTranscript = { ...expectedNormalized, meeting_id: id };
    return HttpResponse.json(body);
  }),

  http.get('*/api/meetings/:id/memory-cards', ({ params, request }) => {
    const id = params.id as string;
    const entry = meetings.get(id);
    if (!entry) return new HttpResponse(null, { status: 404 });
    const url = new URL(request.url);
    const stateFilter = url.searchParams.get('state') as MemoryCardState | null;
    const typeFilter = url.searchParams.get('type') as MemoryCardType | null;
    const items = entry.cards.filter((c) => {
      if (stateFilter && c.state !== stateFilter) return false;
      if (typeFilter && c.type !== typeFilter) return false;
      return true;
    });
    const body: MemoryCardListResponse = { items, total: items.length };
    return HttpResponse.json(body);
  }),

  http.post('*/api/memory-cards', async ({ request }) => {
    const input = (await request.json()) as {
      meeting_id: string;
      type: MemoryCardType;
      title: string;
      content: string;
      speakers?: string[];
      source_chunk_ids?: string[];
    };
    const entry = meetings.get(input.meeting_id);
    if (!entry) return new HttpResponse(null, { status: 404 });
    const now = nowIso();
    const card: MemoryCard = {
      memory_card_id: nextCardId(input.meeting_id),
      meeting_id: input.meeting_id,
      type: input.type,
      state: 'draft',
      title: input.title,
      content: input.content,
      speakers: input.speakers ?? [],
      source_chunk_ids: input.source_chunk_ids ?? [],
      created_at: now,
      updated_at: now,
    };
    entry.cards.push(card);
    return HttpResponse.json(card, { status: 201 });
  }),

  http.patch('*/api/memory-cards/:id', async ({ params, request }) => {
    const found = findCardWithEntry(params.id as string);
    if (!found) return new HttpResponse(null, { status: 404 });
    const patch = (await request.json()) as Partial<MemoryCard>;
    Object.assign(found.card, patch, { updated_at: nowIso() });
    return HttpResponse.json(found.card);
  }),

  http.post('*/api/memory-cards/:id/commit', ({ params }) => {
    const found = findCardWithEntry(params.id as string);
    if (!found) return new HttpResponse(null, { status: 404 });
    found.card.state = 'committed';
    found.card.updated_at = nowIso();
    return HttpResponse.json({ card: found.card });
  }),

  http.post('*/api/memory-cards/:id/reject', ({ params }) => {
    const found = findCardWithEntry(params.id as string);
    if (!found) return new HttpResponse(null, { status: 404 });
    found.card.state = 'rejected';
    found.card.updated_at = nowIso();
    return HttpResponse.json({ card: found.card });
  }),

  http.post('*/api/meetings/:id/finalize', ({ params }) => {
    const id = params.id as string;
    const entry = meetings.get(id);
    if (!entry) return new HttpResponse(null, { status: 404 });
    const now = nowIso();
    entry.meeting.finalized_at = now;
    const body: FinalizeMeetingResponse = { meeting_id: id, finalized_at: now };
    return HttpResponse.json(body);
  }),

  http.post('*/api/qa/meeting', async ({ request }) => {
    const input = (await request.json()) as { meeting_id: string; question: string };
    const isWeak = /\bweak\b/i.test(input.question);
    const citations = ['seg_001', 'seg_002']
      .map(citationFromSegment)
      .filter((c): c is EvidenceCitation => c !== null);
    const body: AskHermesResponse = {
      answer: isWeak
        ? `I can only weakly answer "${input.question}" from the transcript.`
        : `Regarding "${input.question}": the team aligned on shipping the auth migration by end of Q1.`,
      confidence: isWeak ? 0.32 : 0.78,
      citations,
      weak_evidence: isWeak,
    };
    return HttpResponse.json(body);
  }),
];
