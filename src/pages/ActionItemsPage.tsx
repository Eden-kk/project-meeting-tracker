import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { listActionItems } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { useWorkspace } from '../hooks/useWorkspace';
import { ActionItemsTable } from '../components/ActionItemsTable';
import { EmptyState } from '../components/EmptyState';

/** Wave 5.1 — cross-meeting action-items dashboard.
 *
 * Filters: speaker (substring; server uses JSONB `?` contains), source
 * meeting, and a date range over `created_at`. Row click navigates to
 * the source meeting at the cited segment anchor.
 */
export default function ActionItemsPage() {
  return (
    <DashboardView
      title="Action items"
      emptyTitle="No action items yet"
      emptyBody="Action items extracted across all meetings will appear here."
      queryFn={listActionItems}
      queryKey={queryKeys.actionItems}
    />
  );
}

// Internal: the dashboard skeleton is shared with OpenQuestionsPage; both
// pages only differ in the (route, queryKey, label) tuple.
export type DashboardProps = {
  title: string;
  emptyTitle: string;
  emptyBody: string;
  queryFn: typeof listActionItems;
  // Either dashboard query-key factory plugs in here. They share the
  // same parameter shape; the discriminator is the leading string
  // (`actionItems` vs `openQuestions`).
  queryKey: (
    params: Parameters<typeof queryKeys.actionItems>[0],
  ) => readonly unknown[];
};

export function DashboardView({ title, emptyTitle, emptyBody, queryFn, queryKey }: DashboardProps) {
  const { workspaceId } = useWorkspace();
  const [speaker, setSpeaker] = useState('');
  const [meetingId, setMeetingId] = useState('');
  const [since, setSince] = useState('');
  const [until, setUntil] = useState('');

  const params = useMemo(
    () => ({
      workspace_id: workspaceId,
      speaker: speaker.trim() || undefined,
      meeting_id: meetingId.trim() || undefined,
      since: since ? new Date(since).toISOString() : undefined,
      until: until ? new Date(until).toISOString() : undefined,
    }),
    [workspaceId, speaker, meetingId, since, until],
  );

  const { data, isLoading, isError } = useQuery({
    queryKey: queryKey(params),
    queryFn: () => queryFn(params),
  });

  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-semibold">{title}</h1>

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-4">
        <input
          type="search"
          placeholder="Speaker…"
          value={speaker}
          onChange={(e) => setSpeaker(e.target.value)}
          aria-label="Filter by speaker"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          type="search"
          placeholder="Meeting id…"
          value={meetingId}
          onChange={(e) => setMeetingId(e.target.value)}
          aria-label="Filter by meeting id"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          type="date"
          value={since}
          onChange={(e) => setSince(e.target.value)}
          aria-label="From date"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
        <input
          type="date"
          value={until}
          onChange={(e) => setUntil(e.target.value)}
          aria-label="To date"
          className="rounded border border-gray-300 px-3 py-2 text-sm"
        />
      </div>

      {isLoading && <p className="text-sm text-gray-500">Loading…</p>}
      {isError && <p className="text-sm text-red-700">Failed to load.</p>}

      {data && data.items.length === 0 && (
        <EmptyState title={emptyTitle} body={emptyBody} />
      )}
      {data && data.items.length > 0 && (
        <>
          <p className="text-xs text-gray-500">{data.total} total</p>
          <ActionItemsTable rows={data.items} />
        </>
      )}
    </div>
  );
}
