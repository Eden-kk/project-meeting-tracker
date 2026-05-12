/**
 * useWorkspace — single source of truth for the active workspace inside
 * any /ws/:workspaceId/* route.
 *
 * The URL holds the workspace id (no React Context, no global state);
 * this hook is a thin wrapper around `useParams()` + the workspaces-list
 * `useQuery` for ergonomics. `WorkspaceShell` guards every consumer by
 * redirecting away from invalid ids before the children mount, so the
 * non-null assertion below is a compile-safety net rather than a
 * runtime branch — calling the hook outside the workspace route group
 * is a programmer error and throws loudly to surface it.
 */
import { useQuery } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { listWorkspaces, type Workspace } from '../api/client';
import { queryKeys } from '../api/queryKeys';

export type UseWorkspaceReturn = {
  workspaceId: string;
  workspaces: Workspace[];
  currentWorkspace: Workspace | undefined;
  isLoading: boolean;
};

export function useWorkspace(): UseWorkspaceReturn {
  const { workspaceId } = useParams<{ workspaceId: string }>();
  if (!workspaceId) {
    throw new Error(
      'useWorkspace called outside /ws/:workspaceId route',
    );
  }
  const query = useQuery({
    queryKey: queryKeys.workspaces(),
    queryFn: listWorkspaces,
    staleTime: 60_000,
  });
  const workspaces = query.data?.items ?? [];
  const currentWorkspace = workspaces.find((w) => w.id === workspaceId);
  return {
    workspaceId,
    workspaces,
    currentWorkspace,
    isLoading: query.isLoading,
  };
}
