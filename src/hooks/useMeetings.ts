/**
 * useMeetings — public surface for the library list.
 *
 * Prefers the API (`GET /api/meetings`) and falls back to the local
 * registry on network failure so the UI degrades gracefully rather than
 * blanking.  When both have an entry for the same meeting_id, the
 * server's view wins on every field that exists on both sides; the
 * registry contributes only fields the API does not yet expose
 * (imported_at, source_type, last_seen_at) and meetings that exist
 * locally but not on the server (e.g. an in-flight import the server
 * hasn't returned yet).
 */
import { useQuery } from '@tanstack/react-query';
import { listMeetings, type Meeting } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { DEV_WORKSPACE_ID } from '../lib/constants';
import { useMeetingsRegistry } from './useMeetingsRegistry';
import type { StoredMeetingSummary } from '../lib/meetingsRegistry';

const REGISTRY_FALLBACK_FIELDS = {
  source_type: 'pasted_transcript' as StoredMeetingSummary['source_type'],
  imported_at: '',
  last_seen_at: '',
};

export function meetingToSummary(
  meeting: Meeting,
  registryEntry?: StoredMeetingSummary,
): StoredMeetingSummary {
  return {
    meeting_id: meeting.meeting_id,
    artifact_id: meeting.artifact_id,
    title: meeting.title || registryEntry?.title || '',
    status: meeting.status,
    evidence_quality: meeting.evidence_quality,
    detected_pattern:
      meeting.detected_pattern?.primary_pattern ?? registryEntry?.detected_pattern ?? null,
    source_type: registryEntry?.source_type ?? REGISTRY_FALLBACK_FIELDS.source_type,
    imported_at: registryEntry?.imported_at ?? REGISTRY_FALLBACK_FIELDS.imported_at,
    last_seen_at: registryEntry?.last_seen_at ?? REGISTRY_FALLBACK_FIELDS.last_seen_at,
  };
}

export function mergeServerAndRegistry(
  serverItems: Meeting[],
  registry: StoredMeetingSummary[],
): StoredMeetingSummary[] {
  const registryById = new Map(registry.map((r) => [r.meeting_id, r]));
  const serverIds = new Set(serverItems.map((m) => m.meeting_id));
  const merged: StoredMeetingSummary[] = serverItems.map((m) =>
    meetingToSummary(m, registryById.get(m.meeting_id)),
  );
  // Registry-only entries (e.g. an import the server hasn't returned yet)
  // are appended after the server's ordered run so the API drives ordering.
  for (const r of registry) {
    if (!serverIds.has(r.meeting_id)) merged.push(r);
  }
  return merged;
}

export function useMeetings(workspaceId: string = DEV_WORKSPACE_ID): {
  meetings: StoredMeetingSummary[];
  isOffline: boolean;
} {
  const registry = useMeetingsRegistry();
  const query = useQuery({
    queryKey: queryKeys.meetings({ workspace_id: workspaceId }),
    queryFn: () => listMeetings({ workspace_id: workspaceId }),
    retry: false,
  });
  if (query.isError) {
    return { meetings: registry, isOffline: true };
  }
  if (!query.data) {
    return { meetings: registry, isOffline: false };
  }
  return {
    meetings: mergeServerAndRegistry(query.data.items, registry),
    isOffline: false,
  };
}
