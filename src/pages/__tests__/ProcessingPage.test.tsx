import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import ProcessingPage from '../ProcessingPage';
import * as client from '../../api/client';
import type { Meeting } from '../../api/client';

const navigateMock = vi.fn();
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return { ...actual, useNavigate: () => navigateMock };
});

function meetingFixture(overrides: Partial<Meeting>): Meeting {
  return {
    meeting_id: 'm_1',
    artifact_id: 'a_1',
    title: '',
    status: 'processing',
    started_at: null,
    ended_at: null,
    finalized_at: null,
    current_schema: null,
    evidence_quality: 'medium',
    ...overrides,
  };
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/ws/:workspaceId/meetings/:id/processing" element={<ProcessingPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('ProcessingPage', () => {
  beforeEach(() => {
    navigateMock.mockReset();
    vi.restoreAllMocks();
  });

  it('renders Transcribing/parsing as active when meeting is processing', async () => {
    vi.spyOn(client, 'getMeeting').mockResolvedValue(meetingFixture({ status: 'processing' }));
    renderAt('/ws/ws_dev/meetings/m_1/processing');
    expect(await screen.findByText(/transcribing\/parsing/i)).toBeInTheDocument();
  });

  it('navigates to review on ready', async () => {
    vi.spyOn(client, 'getMeeting').mockResolvedValue(meetingFixture({ status: 'ready' }));
    renderAt('/ws/ws_dev/meetings/m_1/processing');
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/ws/ws_dev/meetings/m_1', { replace: true }),
    );
  });

  it('renders Hermes extraction as active when status is finalizing', async () => {
    vi.spyOn(client, 'getMeeting').mockResolvedValue(meetingFixture({ status: 'finalizing' }));
    renderAt('/ws/ws_dev/meetings/m_1/processing');
    // Status timeline marks Hermes extraction with the extracting label
    // when the background task is mid-flight.
    expect(await screen.findByText(/extracting/i)).toBeInTheDocument();
    // Same as `ready`, the user is forwarded to the meeting view so they
    // can read transcript / cards while finalize finishes.
    await waitFor(() =>
      expect(navigateMock).toHaveBeenCalledWith('/ws/ws_dev/meetings/m_1', { replace: true }),
    );
  });

  it('shows failed card with try-again link', async () => {
    vi.spyOn(client, 'getMeeting').mockResolvedValue(meetingFixture({ status: 'failed' }));
    renderAt('/ws/ws_dev/meetings/m_1/processing');
    expect(await screen.findByText(/processing failed/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /try again/i })).toHaveAttribute('href', '/ws/ws_dev/');
  });
});
