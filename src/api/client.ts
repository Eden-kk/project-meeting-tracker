import axios from 'axios';
import type { components } from './types';
import type {
  ActionItemListResponse,
  AskHermesInput,
  AskHermesResponse,
  CreateMemoryCardInput,
  EvidenceCitation,
  FinalizeMeetingResponse,
  FollowupDraftInput,
  FollowupDraftResponse,
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
  workspace_id: string;
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
  fd.append('workspace_id', input.workspace_id);
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
  // The backend serialises the speakers field as `speakers_json`; normalise
  // it to `speakers` so components can rely on the MemoryCard type shape.
  const items = res.data.items.map((card: MemoryCard & { speakers_json?: string[] | null }) => ({
    ...card,
    speakers: card.speakers ?? card.speakers_json ?? [],
  }));
  return { ...res.data, items };
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

// --- live capture (Phase 3 Wave 6.1) -------------------------------------

export type LiveMeetingCreated = {
  artifact_id: string;
  meeting_id: string;
  status: 'live';
};

export type LiveSegment = {
  segment_id: string;
  speaker_id: string | null;
  speaker_name: string | null;
  start_ms: number | null;
  end_ms: number | null;
  text: string;
  confidence: number | null;
  source_type: string;
  is_final: boolean;
};

export type LiveSegmentsResponse = {
  meeting_id: string;
  status: string;
  /** Wave 6.3: rolling agent summary (NULL until the first ~120s tick fires). */
  live_summary: string | null;
  /** Wave 8.6: current discussion topic, updated every ~30s. */
  current_topic: string | null;
  /** Q1: latest 3-5 interview questions; NULL until the first 60s tick fires. */
  suggested_questions: string[] | null;
  segments: LiveSegment[];
};

export type LiveSummaryResponse = {
  meeting_id: string;
  status: string;
  summary: string | null;
};

export type LiveDraftCardsResponse = {
  meeting_id: string;
  status: string;
  /** MemoryCard rows in creation order. The wire field name is
   * ``speakers_json``; we normalise to ``speakers`` so the existing
   * ``MemoryCardItem`` component can consume the result without a
   * second adapter. */
  items: MemoryCard[];
};

export type LiveChunkAccepted = {
  seq: number;
  segments_added: number;
  bytes: number;
  transcribed: boolean;
};

export async function createLiveMeeting(
  workspaceId: string,
  title: string,
  interviewee_name?: string,
  interviewee_role?: string,
): Promise<LiveMeetingCreated> {
  const fd = new FormData();
  fd.append('workspace_id', workspaceId);
  fd.append('title', title);
  if (interviewee_name) fd.append('interviewee_name', interviewee_name);
  if (interviewee_role) fd.append('interviewee_role', interviewee_role);
  const res = await api.post<LiveMeetingCreated>('/api/live-meetings', fd);
  return res.data;
}

export async function uploadLiveChunk(
  meetingId: string,
  blob: Blob,
  seq: number,
): Promise<LiveChunkAccepted> {
  const fd = new FormData();
  fd.append('audio', blob, `chunk-${seq}.webm`);
  const res = await api.post<LiveChunkAccepted>(
    `/api/live-meetings/${meetingId}/audio-chunk`,
    fd,
  );
  return res.data;
}

export async function endLiveMeeting(meetingId: string): Promise<{ status: string }> {
  const res = await api.post<{ status: string }>(
    `/api/live-meetings/${meetingId}/end`,
  );
  return res.data;
}

/** Wave 8.6: rename a speaker label via PATCH /api/meetings/{id}/speakers. */
export async function renameLiveSpeaker(
  meetingId: string,
  from: string,
  to: string,
): Promise<void> {
  await api.patch(`/api/meetings/${meetingId}/speakers`, { from, to });
}

export async function listLiveSegments(
  meetingId: string,
  sinceId?: string | null,
): Promise<LiveSegmentsResponse> {
  const res = await api.get<LiveSegmentsResponse>(
    `/api/live-meetings/${meetingId}/segments`,
    { params: sinceId ? { since_id: sinceId } : undefined },
  );
  return res.data;
}

/**
 * Wave 6.3: standalone read of the rolling agent summary. The same
 * value is bundled into the segments-poll response, so most callers
 * only need this when they want to refresh the summary without paying
 * the segments-list cost.
 */
export async function getLiveSummary(
  meetingId: string,
): Promise<LiveSummaryResponse> {
  const res = await api.get<LiveSummaryResponse>(
    `/api/live-meetings/${meetingId}/summary`,
  );
  return res.data;
}

/**
 * Wave 6.4: poll for memory cards created by the live extraction tick.
 *
 * Pass ``sinceIso`` (the latest ``created_at`` you've already seen) to
 * skip rows you already rendered. Server-side filter is on
 * ``created_at > since`` so the first call (with ``sinceIso=null``)
 * returns everything.
 */
export async function listLiveDraftCards(
  meetingId: string,
  sinceIso: string | null = null,
): Promise<LiveDraftCardsResponse> {
  type RawCard = MemoryCard & { speakers_json?: string[] | null };
  const res = await api.get<{
    meeting_id: string;
    status: string;
    items: RawCard[];
  }>(`/api/live-meetings/${meetingId}/draft-cards`, {
    params: sinceIso ? { since_iso: sinceIso } : undefined,
  });
  // Mirror the normalisation that ``listMeetingCards`` does so callers
  // can rely on the ``speakers`` field shape.
  const items: MemoryCard[] = res.data.items.map((card) => ({
    ...card,
    speakers: card.speakers ?? card.speakers_json ?? [],
  }));
  return { ...res.data, items };
}

export type CardSearchHit = {
  memory_card_id: string;
  meeting_id: string;
  meeting_title: string;
  type: MemoryCardType;
  title: string;
  content: string;
  confidence: number;
  source_start_ms: number | null;
  source_end_ms: number | null;
  snippet: string;
  rank: number;
};

export type CardSearchResponse = {
  items: CardSearchHit[];
  total: number;
};

export type SearchCardsParams = {
  q: string;
  workspace_id: string;
  type?: MemoryCardType;
  limit?: number;
  offset?: number;
};

export type WorkspaceQACitation = {
  meeting_id: string;
  meeting_title: string;
  memory_card_id: string | null;
  segment_id: string | null;
  snippet: string;
};

export type WorkspaceQAResponse = {
  answer: string;
  confidence: number;
  citations: WorkspaceQACitation[];
  weak_evidence: boolean;
};

export type AskWorkspaceInput = {
  workspace_id: string;
  question: string;
};

export async function askWorkspace(
  input: AskWorkspaceInput,
): Promise<WorkspaceQAResponse> {
  // The backend may return either the normalised WorkspaceQAResponse shape
  // {answer, confidence, citations, weak_evidence} or the raw run_skill
  // shape {final_text, tool_calls, iterations} if the workspace-qa skill
  // path bypasses the response wrapper. Normalise here so AskPage can
  // always read `.answer`.
  const res = await api.post<WorkspaceQAResponse & { final_text?: string }>('/api/qa/workspace', {
    workspace_id: input.workspace_id,
    question: input.question,
  });
  const data = res.data;
  if (!data.answer && data.final_text) {
    return {
      answer: data.final_text,
      confidence: (data as unknown as { confidence?: number }).confidence ?? 0.6,
      citations: (data as unknown as { citations?: WorkspaceQACitation[] }).citations ?? [],
      weak_evidence: (data as unknown as { weak_evidence?: boolean }).weak_evidence ?? false,
    };
  }
  return data;
}

export async function searchCards(
  params: SearchCardsParams,
): Promise<CardSearchResponse> {
  const res = await api.get<CardSearchResponse>('/api/search/cards', {
    params: {
      q: params.q,
      workspace_id: params.workspace_id,
      type: params.type,
      limit: params.limit,
      offset: params.offset,
    },
  });
  return res.data;
}

// --- Wave 4.2 — transcript search -------------------------------------------

export type TranscriptSearchHit = {
  segment_id: string;
  meeting_id: string;
  meeting_title: string;
  speaker: string;
  start_ms: number;
  end_ms: number;
  text: string;
  snippet: string;
  rank: number;
};

export type TranscriptSearchResponse = {
  items: TranscriptSearchHit[];
  total: number;
};

export type SearchTranscriptsParams = {
  q: string;
  workspace_id: string;
  limit?: number;
  offset?: number;
};

export async function searchTranscripts(
  params: SearchTranscriptsParams,
): Promise<TranscriptSearchResponse> {
  const res = await api.get<TranscriptSearchResponse>('/api/search/transcripts', {
    params: {
      q: params.q,
      workspace_id: params.workspace_id,
      limit: params.limit,
      offset: params.offset,
    },
  });
  return res.data;
}

// --- Wave 5.1/5.2 — action items / open questions dashboards ----------------

export async function listActionItems(
  params: ListActionItemsParams,
): Promise<ActionItemListResponse> {
  const res = await api.get<ActionItemListResponse>('/api/action-items', { params });
  return res.data;
}

export async function listOpenQuestions(
  params: ListActionItemsParams,
): Promise<ActionItemListResponse> {
  const res = await api.get<ActionItemListResponse>('/api/open-questions', { params });
  return res.data;
}

// --- Workspaces ------------------------------------------------------------

export type Workspace = {
  id: string;
  name: string;
  description: string | null;
  last_meeting_at: string | null;
};

export type WorkspaceListResponse = {
  items: Workspace[];
  total: number;
};

export async function listWorkspaces(): Promise<WorkspaceListResponse> {
  const res = await api.get<WorkspaceListResponse>('/api/workspaces');
  return res.data;
}

// --- Wave 5.3 — follow-up draft ---------------------------------------------

export async function draftFollowup(
  input: FollowupDraftInput,
): Promise<FollowupDraftResponse> {
  const { meeting_id, ...body } = input;
  const res = await api.post<FollowupDraftResponse>(
    `/api/meetings/${meeting_id}/followup-draft`,
    body,
  );
  return res.data;
}
