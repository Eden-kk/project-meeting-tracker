import { describe, it, expect, vi } from 'vitest';
import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useWorkspace } from '../useWorkspace';
import * as client from '../../api/client';

function wrapAt(path: string, qc?: QueryClient) {
  const c = qc ?? new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return {
    wrapper: ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={c}>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/ws/:workspaceId" element={<>{children}</>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>
    ),
  };
}

describe('useWorkspace', () => {
  it('reads workspaceId from the /ws/:workspaceId URL param', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [
        { id: 'ws_alpha', name: 'Alpha', description: null, last_meeting_at: null },
      ],
      total: 1,
    });
    const { result } = renderHook(() => useWorkspace(), wrapAt('/ws/ws_alpha'));
    expect(result.current.workspaceId).toBe('ws_alpha');
    await waitFor(() => expect(result.current.isLoading).toBe(false));
  });

  it('surfaces the matching workspace object from the fetched list', async () => {
    const ws = {
      id: 'ws_alpha',
      name: 'Alpha',
      description: 'Planning',
      last_meeting_at: '2026-05-10T12:00:00Z',
    };
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [
        ws,
        { id: 'ws_other', name: 'Other', description: null, last_meeting_at: null },
      ],
      total: 2,
    });
    const { result } = renderHook(() => useWorkspace(), wrapAt('/ws/ws_alpha'));
    await waitFor(() => expect(result.current.currentWorkspace).toBeDefined());
    expect(result.current.currentWorkspace).toMatchObject({
      id: 'ws_alpha',
      name: 'Alpha',
      description: 'Planning',
    });
    expect(result.current.workspaces).toHaveLength(2);
  });

  it('returns isLoading=true while the workspaces fetch is in flight', () => {
    // Never-resolving promise → query stays in loading.
    vi.spyOn(client, 'listWorkspaces').mockReturnValue(new Promise(() => undefined));
    const { result } = renderHook(() => useWorkspace(), wrapAt('/ws/ws_alpha'));
    expect(result.current.isLoading).toBe(true);
    expect(result.current.workspaces).toEqual([]);
    expect(result.current.currentWorkspace).toBeUndefined();
  });
});
