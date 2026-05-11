import { http, HttpResponse } from 'msw';
import type {
  ImportAccepted,
  Meeting,
  MeetingsList,
  NormalizedTranscript,
} from '../api/client';
import { expectedNormalized, makeFixtureMeeting } from './fixtures';

type Entry = { meeting: Meeting; createdAt: number };

const meetings = new Map<string, Entry>();
const READY_AFTER_MS = 2000;
let counter = 0;

function nextId() {
  counter += 1;
  const stamp = Date.now().toString(36);
  return { meeting_id: `m_${stamp}_${counter}`, artifact_id: `art_${stamp}_${counter}` };
}

function currentStatus(entry: Entry): Meeting['status'] {
  return Date.now() - entry.createdAt >= READY_AFTER_MS ? 'ready' : 'processing';
}

export const handlers = [
  http.post('*/api/conversations/import', async ({ request }) => {
    const ids = nextId();
    const form = await request.formData();
    const title = (form.get('title') as string | null) ?? '';
    const meeting = makeFixtureMeeting(ids.meeting_id, ids.artifact_id, title);
    meetings.set(ids.meeting_id, { meeting, createdAt: Date.now() });
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
];
