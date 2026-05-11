import axios from 'axios';
import type { components } from './types';
import { DEV_WORKSPACE_ID } from '../lib/constants';
import type {
  ActionItemListResponse,
  AskHermesInput,
  AskHermesResponse,
  CreateMemoryCardInput,
  EvidenceCitation,
  FinalizeMeetingResponse,
  ListActionItemsParams,
  MemoryCard,
  MemoryCardListResponse,
  MemoryCardType,
} from './memory_cards.types';

export type {
  AskHermesResponse,
  EvidenceCitation,
  MemoryCard,
  MemoryCardType,
};

export type ImportAccepted = components['schemas']['ImportAccepted'];
export type Meeting = components['schemas']['Meeting'];
export type NormalizedTranscript = components['schemas']['NormalizedTranscript'];
export type SpeakerSegment = components['schemas']['SpeakerSegment'];

export type MeetingsList = { items: Meeting[]; total: number };
export type ListMeetingsParams = { workspace_id: string; limit?: number; offset?: number };

export type Visibility = 'private' | 'workspace' | 'shared';

export type ImportInput = {
  title: string;
  visibility: Visibility;
  labels: string[];
  voice_file?: File;
  transcript_file?: File;
  pasted_transcript?: string;
};

export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE ?? '',
});

export async function importConversation(input: ImportInput): Promise<ImportAccepted> {
  const fd = new FormData();
  fd.append('workspace_id', DEV_WORKSPACE_ID);
  fd.append('title', input.title);
  fd.append('visibility', input.visibility);
  for (const label of input.labels) fd.append('labels', label);
  if (input.voice_file) fd.append('voice_file', input.voice_file);
  if (input.transcript_file) fd.append('transcript_file', input.transcript_file);
  if (input.pasted_transcript !== undefined) fd.append('pasted_transcript', input.pasted_transcript);

  const res = await api.post<ImportAccepted>('/api/conversations/import', fd);
  return res.data;
}

export async function getMeeting(id: string): Promise<Meeting> {
  const res = await api.get<Meeting>(`/api/meetings/${id}`);
  return res.data;
}

export async function getMeetingTranscript(id: string): Promise<NormalizedTranscript> {
  const res = await api.get<NormalizedTranscript>(`/api/meetings/${id}/transcript`);
  return res.data;
}

export async function listMeetings(params: ListMeetingsParams): Promise<MeetingsList> {
  const res = await api.get<MeetingsList>('/api/meetings', { params });
  return res.data;
}

/** Phase-3: state filter is gone; visibility is controlled by `include_hidden`
 * (default false hides agent-soft-deleted rows). */
export type ListMeetingCardsFilters = {
  type?: MemoryCardType;
  include_hidden?: boolean;
};

export async function listMeetingCards(
  meetingId: string,
  filters?: ListMeetingCardsFilters,
): Promise<MemoryCardListResponse> {
  const res = await api.get<MemoryCardListResponse>(
    `/api/meetings/${meetingId}/memory-cards`,
    { params: filters },
  );
  return res.data;
}

export async function createMemoryCard(input: CreateMemoryCardInput): Promise<MemoryCard> {
  const res = await api.post<MemoryCard>('/api/memory-cards', input);
  return res.data;
}

export async function finalizeMeeting(meetingId: string): Promise<FinalizeMeetingResponse> {
  const res = await api.post<FinalizeMeetingResponse>(
    `/api/meetings/${meetingId}/finalize`,
  );
  return res.data;
}

export async function askHermes(input: AskHermesInput): Promise<AskHermesResponse> {
  const res = await api.post<AskHermesResponse>('/api/qa/meeting', input);
  return res.data;
}

/** Wave 5.1 — cross-meeting action-items dashboard. */
export async function listActionItems(
  params: ListActionItemsParams,
): Promise<ActionItemListResponse> {
  const res = await api.get<ActionItemListResponse>('/api/action-items', { params });
  return res.data;
}

/** Wave 5.2 — cross-meeting open-questions dashboard.
 *
 * Same query parameters as `listActionItems`; only the route differs.
 */
export async function listOpenQuestions(
  params: ListActionItemsParams,
): Promise<ActionItemListResponse> {
  const res = await api.get<ActionItemListResponse>('/api/open-questions', { params });
  return res.data;
}
