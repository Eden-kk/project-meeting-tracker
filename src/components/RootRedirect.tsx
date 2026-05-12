/**
 * RootRedirect — handles `/` (and any unmatched non-`/ws/*` path).
 *
 * Resolution order for the target workspace:
 *   1. `localStorage.lastWorkspaceId` if it still appears in the fetched
 *      workspaces list (stale ids are ignored).
 *   2. First workspace in the list (server already sorts by recency).
 *   3. `DEV_WORKSPACE_ID` — last-resort fallback when the workspaces
 *      table is empty (extreme edge case in pre-production).
 */
import { Navigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listWorkspaces } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { DEV_WORKSPACE_ID } from '../lib/constants';

const LAST_WS_KEY = 'lastWorkspaceId';

function readLastWorkspaceId(): string | null {
  try {
    return localStorage.getItem(LAST_WS_KEY);
  } catch {
    return null;
  }
}

export function RootRedirect() {
  const query = useQuery({
    queryKey: queryKeys.workspaces(),
    queryFn: listWorkspaces,
    staleTime: 60_000,
  });

  if (query.isLoading) {
    return (
      <div className="min-h-screen bg-white p-6 text-sm text-gray-500">
        Loading…
      </div>
    );
  }

  const workspaces = query.data?.items ?? [];
  const last = readLastWorkspaceId();
  const lastValid = last && workspaces.some((w) => w.id === last) ? last : null;
  const target =
    lastValid ?? workspaces[0]?.id ?? DEV_WORKSPACE_ID;
  return <Navigate to={`/ws/${target}/`} replace />;
}
