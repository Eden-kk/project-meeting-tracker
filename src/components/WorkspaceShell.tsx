/**
 * WorkspaceShell — the route-level layout that wraps every page under
 * `/ws/:workspaceId/*`.
 *
 * Responsibilities:
 *   1. Validate the URL's workspaceId against the fetched workspaces list.
 *      An unknown id (deleted, mistyped, stale bookmark) redirects to the
 *      first-available workspace in a single `<Navigate>` — never a 500
 *      or blank page.
 *   2. Persist the active workspaceId to `localStorage.lastWorkspaceId`
 *      via an effect so the next `/` visit lands on the same workspace.
 *      The write is in an effect (not during render) because Strict Mode
 *      double-invokes render and we want one write per id change.
 *   3. Render the sidebar nav, top-bar (with the WorkspaceSwitcher in
 *      the slot the old SearchBar used to occupy), and `<Outlet />`.
 *      This absorbs the old `SidebarShell` so there is only one outlet
 *      level in the tree.
 */
import { useEffect } from 'react';
import { Navigate, Outlet, useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { listWorkspaces } from '../api/client';
import { queryKeys } from '../api/queryKeys';
import { MobileSidebar, Sidebar } from './Sidebar';
import { WorkspaceSwitcher } from './WorkspaceSwitcher';

const LAST_WS_KEY = 'lastWorkspaceId';

export function WorkspaceShell() {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  const query = useQuery({
    queryKey: queryKeys.workspaces(),
    queryFn: listWorkspaces,
    staleTime: 60_000,
  });

  // Persist the "last visited" hint so /  → /ws/<lastUsed>/ on next entry.
  // Effect (not bare render) → no double-write in Strict Mode, no write
  // on every paint.
  useEffect(() => {
    if (workspaceId) {
      try {
        localStorage.setItem(LAST_WS_KEY, workspaceId);
      } catch {
        // localStorage disabled (private mode etc.); the entry-redirect
        // falls back to the first workspace.
      }
    }
  }, [workspaceId]);

  // The workspaces list is in flight on first visit; show a minimal
  // placeholder rather than rendering the shell with an "unknown"
  // workspace.
  if (query.isLoading) {
    return (
      <div className="min-h-screen bg-white text-gray-900">
        <p className="p-6 text-sm text-gray-500">Loading…</p>
      </div>
    );
  }

  const workspaces = query.data?.items ?? [];
  const valid =
    workspaceId !== undefined && workspaces.some((w) => w.id === workspaceId);
  if (!valid && workspaces.length > 0) {
    // Stale or bogus workspaceId in the URL → redirect to the first
    // available (sorted by recency on the server).
    return <Navigate to={`/ws/${workspaces[0].id}/`} replace />;
  }

  return (
    <div className="min-h-screen bg-white text-gray-900">
      <MobileSidebar />
      <div className="flex">
        <Sidebar />
        <main className="min-w-0 flex-1 px-4 py-6 md:px-8">
          <div className="mx-auto max-w-6xl">
            <div className="mb-4 hidden justify-end md:flex">
              <WorkspaceSwitcher />
            </div>
            <Outlet />
          </div>
        </main>
      </div>
    </div>
  );
}
