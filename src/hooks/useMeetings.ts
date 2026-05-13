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
import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listMeetings, type Meeting } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { useWorkspace } from './useWorkspace';
import { useMeetingsRegistry } from './useMeetingsRegistry';
import { remove as removeFromRegistry, type StoredMeetingSummary } from '../lib/meetingsRegistry';

// Registry-only entries this old without server confirmation are stale
// (the import path upserts immediately on POST, so >5 min unconfirmed
// means the server-side import failed or the row was deleted).
const REGISTRY_GRACE_MS = 5 * 60 * 1000;

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
  workspaceId: string,
): { merged: StoredMeetingSummary[]; staleIds: string[] } {
  const registryById = new Map(registry.map((r) => [r.meeting_id, r]));
  const serverIds = new Set(serverItems.map((m) => m.meeting_id));
  const merged: StoredMeetingSummary[] = serverItems.map((m) =>
    meetingToSummary(m, registryById.get(m.meeting_id)),
  );
  // Registry-only entries (e.g. an in-flight import the server hasn't
  // returned yet) are appended within a grace window so optimistic UI
  // works during the import → finalize race. Filtered by workspace_id so
  // a meeting imported in workspace A never leaks into workspace B's list.
  // Legacy entries with no workspace_id are treated as stale and pruned
  // (they predate the workspace-switcher slice).
  const cutoff = Date.now() - REGISTRY_GRACE_MS;
  const staleIds: string[] = [];
  for (const r of registry) {
    if (serverIds.has(r.meeting_id)) continue;
    // Legacy entry with no workspace_id (predates the workspace-switcher
    // slice) — prune; it has no way to be correctly attributed.
    if (!r.workspace_id) {
      staleIds.push(r.meeting_id);
      continue;
    }
    // Different workspace than the one currently being viewed: don't
    // display, don't prune (the entry belongs to that other workspace
    // and will be merged correctly when the user switches there).
    if (r.workspace_id !== workspaceId) continue;
    // Same workspace: check the grace window.
    const ts = Date.parse(r.last_seen_at || r.imported_at || '');
    if (Number.isFinite(ts) && ts >= cutoff) {
      merged.push(r);
    } else {
      staleIds.push(r.meeting_id);
    }
  }
  return { merged, staleIds };
}

export function useMeetings(): {
  meetings: StoredMeetingSummary[];
  isOffline: boolean;
} {
  const { workspaceId } = useWorkspace();
  const registry = useMeetingsRegistry();
  const query = useQuery({
    queryKey: queryKeys.meetings({ workspace_id: workspaceId }),
    queryFn: () => listMeetings({ workspace_id: workspaceId }),
    retry: false,
  });
  const serverItems = query.data?.items;
  const { merged, staleIds } =
    serverItems !== undefined
      ? mergeServerAndRegistry(serverItems, registry, workspaceId)
      : {
          merged: registry.filter((r) => r.workspace_id === workspaceId),
          staleIds: [] as string[],
        };

  // Side-effect: prune stale registry entries (server is authoritative).
  // Runs only after a successful server response — never during
  // offline/loading states, so we never delete entries the server
  // simply hasn't seen yet because of a network error.
  useEffect(() => {
    if (staleIds.length === 0) return;
    for (const id of staleIds) removeFromRegistry(id);
  }, [staleIds.join(',')]);

  // Offline / loading: still scope the fallback list by workspace so a
  // network blip doesn't briefly show entries from other workspaces.
  const ownRegistry = registry.filter((r) => r.workspace_id === workspaceId);
  if (query.isError) {
    return { meetings: ownRegistry, isOffline: true };
  }
  if (!query.data) {
    return { meetings: ownRegistry, isOffline: false };
  }
  return { meetings: merged, isOffline: false };
}
