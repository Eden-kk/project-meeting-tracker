import { describe, expect, it, vi, beforeEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import LivePage from '../LivePage';
import * as client from '../../api/client';

// MediaRecorder + getUserMedia are JSDOM-unfriendly; the recording flow is
// validated manually via the handbook + by Playwright with a mocked backend.
// This test only asserts the idle render so we still catch trivial regressions
// (missing copy, broken JSX, etc.).
describe('LivePage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(client, 'listWorkspaces').mockResolvedValue({
      items: [{ id: 'ws_dev', name: 'Default', description: null, last_meeting_at: null }],
      total: 1,
    });
  });

  it('renders the idle controls', () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={['/ws/ws_dev/live']}>
          <Routes>
            <Route path="/ws/:workspaceId/live" element={<LivePage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(
      screen.getByRole('heading', { name: /live meeting/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole('button', { name: /start meeting/i }),
    ).toBeInTheDocument();
    // Slice-5: the LivePage now renders a second "Meeting title" field on
    // the ZoomUrlForm in idle phase. Pin the assertion to the page-level
    // input by its anchor id so the two don't collide.
    expect(screen.getByLabelText(/^title$/i)).toHaveValue('Live meeting');
    expect(screen.getByTestId('live-phase')).toHaveTextContent('idle');
  });
});
