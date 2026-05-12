import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Outlet, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RootRedirect } from '../RootRedirect';
import * as client from '../../api/client';

function LocationProbe() {
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}</div>;
}

function PageStub({ id }: { id: string }) {
  return <div data-testid={`page-${id}`}>page-{id}</div>;
}

function renderRoot() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/']}>
        <Routes>
          <Route path="/" element={<RootRedirect />} />
          <Route path="/ws/:workspaceId" element={<RouteCapture />}>
            <Route index element={<PageStub id="home" />} />
          </Route>
        </Routes>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

// Tiny shim that just yields to the index child. We don't mount the real
// WorkspaceShell here — we only want to assert the redirect target.
function RouteCapture() {
  return <Outlet />;
}

describe('RootRedirect', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
  });

  it('redirects to localStorage.lastWorkspaceId when valid', async () => {
    localStorage.setItem('lastWorkspaceId', 'ws_beta');
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [
        { id: 'ws_alpha', name: 'Alpha', description: null, last_meeting_at: null },
        { id: 'ws_beta', name: 'Beta', description: null, last_meeting_at: null },
      ],
      total: 2,
    });
    renderRoot();
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/ws/ws_beta/');
    });
  });

  it('falls back to the first workspace when localStorage is stale', async () => {
    localStorage.setItem('lastWorkspaceId', 'ws_does_not_exist');
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [
        { id: 'ws_alpha', name: 'Alpha', description: null, last_meeting_at: null },
        { id: 'ws_beta', name: 'Beta', description: null, last_meeting_at: null },
      ],
      total: 2,
    });
    renderRoot();
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/ws/ws_alpha/');
    });
  });

  it('falls back to DEV_WORKSPACE_ID when both empty', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [],
      total: 0,
    });
    renderRoot();
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/ws/ws_dev/');
    });
  });
});
