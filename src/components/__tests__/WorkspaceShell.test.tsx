import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WorkspaceShell } from '../WorkspaceShell';
import * as client from '../../api/client';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}</div>;
}

function PageStub() {
  return <div data-testid="page-stub">page</div>;
}

function renderAt(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/ws/:workspaceId" element={<WorkspaceShell />}>
            <Route index element={<PageStub />} />
          </Route>
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('WorkspaceShell', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('redirects to the first available workspace when the URL id is unknown', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [
        { id: 'ws_alpha', name: 'Alpha', description: null, last_meeting_at: null },
      ],
      total: 1,
    });
    renderAt('/ws/ws_does_not_exist');
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/ws/ws_alpha/');
    });
  });

  it('writes the valid workspaceId to localStorage on mount', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [
        { id: 'ws_alpha', name: 'Alpha', description: null, last_meeting_at: null },
      ],
      total: 1,
    });
    renderAt('/ws/ws_alpha');
    await waitFor(() => {
      expect(screen.getByTestId('page-stub')).toBeInTheDocument();
    });
    expect(localStorage.getItem('lastWorkspaceId')).toBe('ws_alpha');
  });
});
