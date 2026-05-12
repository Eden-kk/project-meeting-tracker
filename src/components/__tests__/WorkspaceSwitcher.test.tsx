import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { WorkspaceSwitcher, buildSwitchPath } from '../WorkspaceSwitcher';
import * as client from '../../api/client';

const WORKSPACES = [
  { id: 'ws_alpha', name: 'Alpha', description: 'Planning', last_meeting_at: '2026-05-10T12:00:00Z' },
  { id: 'ws_beta', name: 'Beta', description: null, last_meeting_at: null },
];

function LocationProbe() {
  // Renders the current pathname so tests can assert navigations.
  const loc = useLocation();
  return <div data-testid="loc">{loc.pathname}</div>;
}

function renderAt(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route
            path="/ws/:workspaceId/*"
            element={
              <>
                <WorkspaceSwitcher />
                <LocationProbe />
              </>
            }
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('buildSwitchPath', () => {
  it('preserves a safe top-level segment', () => {
    expect(buildSwitchPath('/ws/a/action-items', 'b')).toBe('/ws/b/action-items');
    expect(buildSwitchPath('/ws/a/ask', 'b')).toBe('/ws/b/ask');
    expect(buildSwitchPath('/ws/a/meetings', 'b')).toBe('/ws/b/meetings');
  });
  it('drops workspace-scoped ids from deeper paths', () => {
    expect(buildSwitchPath('/ws/a/meetings/m_xyz', 'b')).toBe('/ws/b/meetings');
    expect(buildSwitchPath('/ws/a/meetings/m_xyz/processing', 'b')).toBe('/ws/b/meetings');
    expect(buildSwitchPath('/ws/a/processing/p_1', 'b')).toBe('/ws/b/processing');
  });
  it('collapses to workspace root on entry-level or unknown top segments', () => {
    expect(buildSwitchPath('/ws/a', 'b')).toBe('/ws/b/');
    expect(buildSwitchPath('/ws/a/', 'b')).toBe('/ws/b/');
    expect(buildSwitchPath('/ws/a/weird-page', 'b')).toBe('/ws/b/');
  });
});

describe('WorkspaceSwitcher', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('renders the current workspace name on the button', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({ items: WORKSPACES, total: 2 });
    renderAt('/ws/ws_alpha/action-items');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /switch workspace/i })).toHaveTextContent('Alpha');
    });
  });

  it('opens the dropdown listing every workspace on click', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({ items: WORKSPACES, total: 2 });
    const user = userEvent.setup();
    renderAt('/ws/ws_alpha/action-items');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /switch workspace/i })).toHaveTextContent('Alpha');
    });
    await user.click(screen.getByRole('button', { name: /switch workspace/i }));
    expect(screen.getByRole('listbox')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-item-ws_alpha')).toBeInTheDocument();
    expect(screen.getByTestId('workspace-item-ws_beta')).toBeInTheDocument();
  });

  it('clicking a workspace navigates to the same sub-path under the new id', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({ items: WORKSPACES, total: 2 });
    const user = userEvent.setup();
    renderAt('/ws/ws_alpha/action-items');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /switch workspace/i })).toHaveTextContent('Alpha');
    });
    await user.click(screen.getByRole('button', { name: /switch workspace/i }));
    await user.click(screen.getByTestId('workspace-item-ws_beta'));
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/ws/ws_beta/action-items');
    });
  });

  it('switching from a meeting-detail URL drops the workspace-scoped id', async () => {
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({ items: WORKSPACES, total: 2 });
    const user = userEvent.setup();
    renderAt('/ws/ws_alpha/meetings/m_xyz');
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /switch workspace/i })).toHaveTextContent('Alpha');
    });
    await user.click(screen.getByRole('button', { name: /switch workspace/i }));
    await user.click(screen.getByTestId('workspace-item-ws_beta'));
    await waitFor(() => {
      expect(screen.getByTestId('loc')).toHaveTextContent('/ws/ws_beta/meetings');
    });
    expect(screen.getByTestId('loc').textContent).not.toContain('m_xyz');
  });
});
