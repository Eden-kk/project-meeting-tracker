import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import MeetingReviewPage from '../MeetingReviewPage';
import * as client from '../../api/client';
import type { Meeting, NormalizedTranscript } from '../../api/client';
import { expectedNormalized } from '../../mocks/fixtures';

function meetingFixture(): Meeting {
  return {
    meeting_id: 'm_fixture001',
    artifact_id: 'art_fixture001',
    title: 'Fixture meeting',
    status: 'ready',
    started_at: null,
    ended_at: null,
    finalized_at: null,
    current_schema: null,
    evidence_quality: 'medium',
  };
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/meetings/:id" element={<MeetingReviewPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe('MeetingReviewPage', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    localStorage.clear();
    vi.spyOn(client, 'getMeeting').mockResolvedValue(meetingFixture());
    vi.spyOn(client, 'getMeetingTranscript').mockResolvedValue(
      expectedNormalized as NormalizedTranscript,
    );
    vi.spyOn(client, 'listMeetingCards').mockResolvedValue({ items: [], total: 0 });
  });

  it('renders all fixture segments in Transcript tab', async () => {
    renderAt('/meetings/m_fixture001');
    const rows = await screen.findAllByTestId('transcript-row');
    expect(rows).toHaveLength(expectedNormalized.segments.length);
  });

  it('only Share / Export remains disabled; Memory and Ask are active', async () => {
    renderAt('/meetings/m_fixture001');
    const share = await screen.findByRole('tab', { name: /share \/ export/i });
    expect(share).toHaveAttribute('aria-disabled', 'true');
    expect(share).toHaveAttribute('title', 'Arrives in Phase 8');
    const memory = screen.getByRole('tab', { name: /memory cards/i });
    expect(memory).not.toHaveAttribute('aria-disabled', 'true');
    const ask = screen.getByRole('tab', { name: /ask hermes/i });
    expect(ask).not.toHaveAttribute('aria-disabled', 'true');
  });

  it('Summary tab shows placeholder copy', async () => {
    const user = userEvent.setup();
    renderAt('/meetings/m_fixture001');
    await waitFor(() => screen.getAllByTestId('transcript-row'));
    await user.click(screen.getByRole('tab', { name: /^summary$/i }));
    expect(
      screen.getByText(/summary not yet available — extraction lands in phase 2/i),
    ).toBeInTheDocument();
  });
});
