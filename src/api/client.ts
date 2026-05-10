import axios from 'axios';
import type { components } from './types';
import { DEV_WORKSPACE_ID } from '../lib/constants';

export type ImportAccepted = components['schemas']['ImportAccepted'];
export type Meeting = components['schemas']['Meeting'];
export type NormalizedTranscript = components['schemas']['NormalizedTranscript'];
export type SpeakerSegment = components['schemas']['SpeakerSegment'];

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
