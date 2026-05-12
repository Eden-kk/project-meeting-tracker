import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MobileSidebar, Sidebar } from '../Sidebar';
import * as client from '../../api/client';

function renderUnderWorkspace(component: JSX.Element) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
    items: [{ id: 'ws_dev', name: 'Default', description: null, last_meeting_at: null }],
    total: 1,
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={['/ws/ws_dev']}>
        <Routes>
          <Route path="/ws/:workspaceId/*" element={component} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('Sidebar (desktop)', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  it('renders nav links prefixed with the active workspace id', () => {
    renderUnderWorkspace(<Sidebar />);
    expect(screen.getByRole('link', { name: 'Home' })).toHaveAttribute('href', '/ws/ws_dev/');
    expect(screen.getByRole('link', { name: 'Meetings' })).toHaveAttribute('href', '/ws/ws_dev/meetings');
    expect(screen.getByRole('link', { name: 'Import' })).toHaveAttribute('href', '/ws/ws_dev/import');
    expect(screen.getByRole('link', { name: 'Settings' })).toHaveAttribute('href', '/ws/ws_dev/settings');
  });
});

describe('MobileSidebar', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });
  it('opens drawer on click and closes on Escape, returning focus to toggle', async () => {
    const user = userEvent.setup();
    renderUnderWorkspace(<MobileSidebar />);
    const toggle = screen.getByRole('button', { name: /open menu/i });
    expect(toggle).toHaveAttribute('aria-expanded', 'false');

    await user.click(toggle);
    expect(toggle).toHaveAttribute('aria-expanded', 'true');
    const dialog = screen.getByRole('dialog');
    expect(dialog).toBeInTheDocument();

    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(toggle).toHaveAttribute('aria-expanded', 'false');
    expect(document.activeElement).toBe(toggle);
  });
});
